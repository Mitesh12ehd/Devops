import requests
import smtplib
import os
import paramiko
import linode_api4
import time
import schedule

EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
LINODE_API_TOKEN = os.environ.get("LINODE_API_TOKEN")

def send_email(email_msg):
    with smtplib.SMTP("smtp.gmail.com",587) as smtp:
        smtp.starttls()
        smtp.ehlo()
        smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        smtp.sendmail(EMAIL_ADDRESS, "miteshchavda57@gmail.com",email_msg)

def restart_container():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname="172.105.54.208", 
        username="root",
        key_filename="/home/mitesh/.ssh/id_rsa"
    )
    stdin, stdout, stderr = ssh.exec_command("docker start 7ea6d3252abc")
    ssh.close()
    print(stdout.readlines())
    print("Application restarted")

def monitor_application():
    try:
        response = requests.get("http://172.105.54.208:8080/")

        # tls is encrypt the communication between python to email server

        if response.status_code == 200:
            print("Nginx application is running")
        else:
            print("Application Down fix it")
            email_msg = "Subject: SITE DOWN\nApplication returned " + str(response.status_code) + " Fix the issue! Restart the application"
            send_email(email_msg)

            # restart application
            restart_container()

    except Exception as e:
        print("Connection error")
        print(e)
        email_msg = "Subject: SITE DOWN\nApplication is not accessible at all."
        send_email(email_msg)

        # restart linode server
        print("Restarting the server")
        client = linode_api4.LinodeClient(LINODE_API_TOKEN)
        nginx_server = client.load(linode_api4.Instance, 94172896)     # Linode ID = ID of our server (instance on linode)
        nginx_server.reboot()

        # restart application
        while True: 
            nginx_server = client.load(linode_api4.Instance, 94172896)
            if(nginx_server.status == "running"):
                time.sleep(5)
                restart_container()
                break

schedule.every(5).seconds.do(monitor_application)
while True:
    schedule.run_pending()
    time.sleep(1)
import boto3
import schedule

ec2_client = boto3.client('ec2', region_name = "ap-south-1")
ec2_resource = boto3.resource('ec2', region_name = "ap-south-1")

def check_instance_status():
    statuses = ec2_client.describe_instance_status(
        IncludeAllInstances = True
    )
    for status in statuses['InstanceStatuses']:
        ins_status = status['InstanceStatus']['Status']
        sys_status = status['SystemStatus']['Status']
        state = status["InstanceState"]
        print(f"Instance {status['InstanceId']} is {state} status is {ins_status} and system status is {sys_status}")

schedule.every(5).minutes.do(check_instance_status)

while True:
    schedule.run_pending()
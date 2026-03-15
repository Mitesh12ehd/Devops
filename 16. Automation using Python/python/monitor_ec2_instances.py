import boto3

ec2_client = boto3.client('ec2', region_name = "ap-south-1")
ec2_resource = boto3.resource('ec2', region_name = "ap-south-1")

reservations = ec2_client.describe_instances()
for reservation in reservations["Reservations"]:
    instances = reservation["Instances"]
    for instance in instances:
        print(instance["InstanceId"],instance["State"]["Name"])

statuses = ec2_client.describe_instance_status()
for status in statuses['InstanceStatuses']:
    ins_status = status['InstanceStatus']['Status']
    sys_status = status['SystemStatus']['Status']
    state = status["InstanceState"]
    print(f"Instance {status['InstanceId']} is {state} status is {ins_status} and system status is {sys_status}")
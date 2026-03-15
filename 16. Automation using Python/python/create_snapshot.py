import boto3
import schedule

ec2_client = boto3.client("ec2", region_name = "ap-south-1")

def create_snapshots():
    volumes = ec2_client.describe_volumes(
        # Filter to ignore other volume of ec2 server than production
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': [
                    'production',
                ]
            },
        ]
    )

    for volume in volumes["Volumes"]:
        new_snapshot = ec2_client.create_snapshot(
            VolumeId=volume["VolumeId"]
        )
        print(new_snapshot)

schedule.every().day.do(create_snapshots)
while True:
    schedule.run_pending()
import boto3
import schedule
from operator import itemgetter

ec2_client = boto3.client("ec2", region_name = "ap-south-1")

# Get volume (of EC2 machines) on which we are created snapshots
volumes = ec2_client.describe_volumes(
    # Filter to ignore other server than production
    Filters=[
        {
            'Name': 'tag:Name',
            'Values': [
                'production',
            ]
        },
    ]
)

def delete_old_snapshots():

    for volume in volumes["Volumes"]:

        response = ec2_client.describe_snapshots(
            OwnerIds=[
                'self',
            ],
            Filters=[
                {
                    'Name': 'volume-id',
                    'Values': [
                        volume["VolumeId"],
                    ]
                },
            ]
        )

        snapshots = response["Snapshots"]

        sorted_by_date = sorted(snapshots, key = itemgetter("StartTime"), reverse=True)

        # Delete snapshots and skip first 2 snapshot in deletion
        for snapshot in sorted_by_date[2:]:
            print(snapshot["SnapshotId"])
            print(snapshot["StartTime"])
            
            response = ec2_client.delete_snapshot(
                SnapshotId= snapshot["SnapshotId"],
            )

            print(response)

schedule.every().day.do(delete_old_snapshots)
while True:
    schedule.run_pending()
import boto3
from operator import itemgetter
import time

ec2_client = boto3.client("ec2",region_name="ap-south-1")
ec2_resource = boto3.resource('ec2', region_name = "ap-south-1")

# ec2 instance id of which we want to restore volume
instance_id = "i-04f01be7a765eaf7e"

# Find current volume of EC2 instance
volumes = ec2_client.describe_volumes(
    Filters=[
        {
            'Name': 'attachment.instance-id',
            'Values': [
                instance_id
            ]
        },
    ]
)
instance_volume = volumes["Volumes"][0]

# Find most recent snapshots
snapshots = ec2_client.describe_snapshots(
    OwnerIds=[
        'self',
    ],
    Filters=[
        {
            'Name': 'volume-id',
            'Values': [
                instance_volume["VolumeId"]
            ]
        },
    ]
)
latest_snapshot = sorted(snapshots["Snapshots"], key = itemgetter("StartTime"), reverse=True)[0]

# Create new volume from snapshot
new_volume = ec2_client.create_volume(
    AvailabilityZone='ap-south-1a',
    SnapshotId = latest_snapshot["SnapshotId"],
    TagSpecifications=[
        {
            'ResourceType': 'volume',
            'Tags': [
                {
                    'Key': 'Name',
                    'Value': 'production'
                },
            ]
        },
    ]
)

# wait for new volume to be in available state
while True:
    vol = ec2_resource.Volume(new_volume["VolumeId"])
    print(vol.state)
    if(vol.state == "available"):
        # Attach new volume to EC2 instance
        ec2_resource.Instance(instance_id).attach_volume(
            Device = "/dev/xvdb",
            VolumeId = new_volume["VolumeId"]
        )
        break
    time.sleep(5)
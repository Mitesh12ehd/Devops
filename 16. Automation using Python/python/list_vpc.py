import boto3

# List all vpc in current region
ec2_client = boto3.client('ec2', region_name = "ap-south-1")

available_vpc = ec2_client.describe_vpcs()
vpcs = available_vpc["Vpcs"]

for vpc in vpcs:
    print(vpc["VpcId"])
    cidr_block_assco_sets = vpc["CidrBlockAssociationSet"]
    for assco_set in cidr_block_assco_sets:
        print(assco_set["CidrBlockState"])
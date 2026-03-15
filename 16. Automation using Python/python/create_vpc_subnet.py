import boto3

ec2_resource = boto3.resource('ec2', region_name = "ap-south-1")

# resource gives object that we use to make subsequent calls
created_vpc = ec2_resource.create_vpc(
    CidrBlock='10.0.0.0/16'
)
created_vpc.create_subnet(
    CidrBlock='10.0.1.0/24'
)
created_vpc.create_tags(
    Tags=[
        {
            'Key': 'Name',
            'Value': 'my-vpc'
        },
    ]
)
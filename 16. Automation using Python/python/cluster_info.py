import boto3

eks_client = boto3.client("eks", region_name = "ap-south-1")

clusters = eks_client.list_clusters()["clusters"]

for cluster in clusters:
    response = eks_client.describe_cluster(
        name = cluster
    )
    cluster_info = response["cluster"]
    cluster_status = cluster_info["status"]
    cluster_endpoint = cluster_info["endpoint"]
    cluster_version = cluster_info["version"]
    print("Cluster: " + cluster + ", Status:" + cluster_status + " , Endpoint:" + cluster_endpoint 
        + ", Cluster version: " + cluster_version)
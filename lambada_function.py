import boto3

def lambda_handler(event, context):
    ec2 = boto3.client('ec2', region_name='ap-south-1')
    
    # Scan the entire account for instances that have the 'Action: AutoStop' tag and are currently running
    print("Searching for instances to optimize...")
    instances = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:Action', 'Values': ['AutoStop']}
        ]
    )
    
    instances_to_stop = []
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instances_to_stop.append(instance['InstanceId'])
            
    if instances_to_stop:
        print(f"Cost Optimizer triggered! Shutting down {len(instances_to_stop)} idle instances: {instances_to_stop}")
        ec2.stop_instances(InstanceIds=instances_to_stop)
        return {"statusCode": 200, "body": f"Successfully stopped {len(instances_to_stop)} instances to save costs."}
    else:
        print("No idle instances found. Everything is fully optimized!")
        return {"statusCode": 200, "body": "No instances to stop."}

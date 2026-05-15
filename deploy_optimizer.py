import boto3
import json
import time
import zipfile
import os
import random
import string

def generate_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

def deploy_cost_optimizer():
    iam = boto3.client('iam')
    lam = boto3.client('lambda', region_name='ap-south-1')
    events = boto3.client('events', region_name='ap-south-1')
    ec2 = boto3.client('ec2', region_name='ap-south-1')
    ssm = boto3.client('ssm', region_name='ap-south-1')

    # Generating unique IDs for resources so you can run this script safely multiple times
    uid = generate_id()
    role_name = f"Lambda-EC2-Optimizer-Role-{uid}"
    lambda_name = f"CostOptimizerFunction-{uid}"
    rule_name = f"Daily-AutoStop-Rule-{uid}"

    print("Starting Automated Cost Optimizer Deployment...")

    # 1. IAM Role for Lambda
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
    }
    print("[INFO] Creating IAM Role for Lambda...")
    role_response = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust_policy))
    role_arn = role_response['Role']['Arn']

    # Attach policies: Basic Execution (CloudWatch Logs) + Custom EC2 Stop Permissions
    iam.attach_role_policy(RoleName=role_name, PolicyArn='arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole')
    
    ec2_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["ec2:DescribeInstances", "ec2:StopInstances"], "Resource": "*"}
        ]
    }
    iam.put_role_policy(RoleName=role_name, PolicyName='EC2StopPolicy', PolicyDocument=json.dumps(ec2_policy))
    print(f"[OK] IAM Role '{role_name}' created with EC2 stop permissions.")

    # We must wait for IAM propagation. If we deploy the Lambda immediately, AWS might say the role doesn't exist yet.
    print("[INFO] Waiting 10 seconds for IAM Profile to propagate globally...")
    time.sleep(10)

    # 2. Package Lambda Code
    print("[INFO] Packaging Lambda Function code...")
    lambda_code = """import boto3

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
"""
    with open('lambda_function.py', 'w') as f:
        f.write(lambda_code)
        
    with zipfile.ZipFile('function.zip', 'w') as zipf:
        zipf.write('lambda_function.py')

    # 3. Create Lambda Function
    print(f"[INFO] Deploying Serverless Lambda Function '{lambda_name}'...")
    with open('function.zip', 'rb') as f:
        zip_content = f.read()
        
    # Implementing a retry mechanism because IAM roles can take up to 60 seconds to propagate
    for attempt in range(12):
        try:
            lambda_response = lam.create_function(
                FunctionName=lambda_name,
                Runtime='python3.12',
                Role=role_arn,
                Handler='lambda_function.lambda_handler',
                Code={'ZipFile': zip_content},
                Timeout=15
            )
            break
        except Exception as e:
            if 'The role defined for the function cannot be assumed by Lambda' in str(e):
                print(f"[RETRY] AWS IAM Role still propagating. Retrying in 10 seconds... (Attempt {attempt+1}/12)")
                time.sleep(10)
            else:
                raise e
    else:
        print("Error: Failed to deploy Lambda function. IAM role propagation timed out.")
        return
        
    lambda_arn = lambda_response['FunctionArn']
    print("[OK] Lambda Function deployed.")

    # 4. Create CloudWatch Event Rule (EventBridge)
    # We set it to run every 5 minutes for demo purposes. In production, this would be a Cron schedule (e.g., 6 PM daily).
    print(f"[INFO] Creating CloudWatch Event Schedule '{rule_name}'...")
    rule_response = events.put_rule(
        Name=rule_name,
        ScheduleExpression='rate(5 minutes)',
        State='ENABLED',
        Description='Triggers the Cost Optimizer Lambda every 5 minutes'
    )
    
    # Grant CloudWatch Event permission to invoke the Lambda
    lam.add_permission(
        FunctionName=lambda_name,
        StatementId=f"AllowCloudWatchInvoke-{uid}",
        Action='lambda:InvokeFunction',
        Principal='events.amazonaws.com',
        SourceArn=rule_response['RuleArn']
    )
    
    # Wire the Event Rule to the Lambda Function
    events.put_targets(
        Rule=rule_name,
        Targets=[{'Id': '1', 'Arn': lambda_arn}]
    )
    print("[OK] CloudWatch Event trigger successfully wired to Lambda.")

    # 5. Launch a Dummy EC2 Instance to demonstrate the cost savings
    print("[INFO] Launching a dummy EC2 instance to test the Auto-Stop functionality...")
    response = ssm.get_parameter(Name='/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2')
    ami_id = response['Parameter']['Value']

    instances = ec2.run_instances(
        ImageId=ami_id,
        InstanceType='t3.micro',
        MinCount=1,
        MaxCount=1,
        # The secret sauce: We tag it with Action=AutoStop
        TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': f'Expensive-Server-{uid}'}, {'Key': 'Action', 'Value': 'AutoStop'}]}]
    )
    instance_id = instances['Instances'][0]['InstanceId']
    print(f"[OK] Test EC2 Instance {instance_id} launched with 'Action: AutoStop' tag.")

    print("\n============================================================")
    print("Automated Cost Optimizer Deployment Complete!")
    print(f"Lambda Function: {lambda_name}")
    print(f"CloudWatch Rule: {rule_name} (Runs every 5 minutes)")
    print(f"Test EC2 Server: {instance_id}")
    print(f"\nThe EC2 server is currently booting up. In less than 5 minutes, CloudWatch will automatically trigger the Lambda function to shut it down and save you money!")
    print("============================================================")

if __name__ == "__main__":
    deploy_cost_optimizer()

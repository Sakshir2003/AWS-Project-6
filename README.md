# AWS-Project-6
# Automated Cost Optimizer

This project demonstrates how to significantly reduce an AWS bill by automatically identifying and shutting down idle or non-production servers after hours. It uses **Serverless** architecture to achieve this.

## Architecture & Services Used
1. **AWS Lambda**: Contains the serverless Python code that utilizes Boto3 to scan the entire AWS account. It looks for any EC2 instances that are currently `running` and possess the specific tag `Action: AutoStop`.
2. **Amazon EventBridge (CloudWatch Events)**: Acts as the cron-job scheduler. It is configured to automatically trigger the Lambda function at regular intervals (set to every 5 minutes for demonstration purposes).
3. **AWS IAM**: Provides a highly-restrictive role to the Lambda function, strictly limiting its permissions to `ec2:DescribeInstances` and `ec2:StopInstances`.
4. **Amazon EC2**: The deployment script spins up a dummy EC2 server with the `Action: AutoStop` tag so you can watch the Lambda function terminate it automatically!

## How to Test It
Deploy the full automation stack using Boto3:
```powershell
python deploy_optimizer.py
```

Wait 5 minutes after deploying. Go to the EC2 Dashboard in your AWS Console, and you will see the `Expensive-Server` transition from **Running** to **Stopped** on its own!

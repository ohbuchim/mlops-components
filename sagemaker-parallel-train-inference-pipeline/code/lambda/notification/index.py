import yaml
import boto3
import json
from datetime import datetime
from dateutil import tz
import os

sns_client = boto3.client('sns')


def publish_message(sns_topic_arn, message, subject):
    response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Message=message,
        Subject=subject
    )

    return response


def lambda_handler(event, context):
    JST = tz.gettz('Asia/Tokyo')
    timestamp = datetime.now(JST).strftime('%Y%m%d-%H%M%S')

    print('event', event)
    print('context', context)

    status = event['status']
    job_name = event['param']['ProcessingJobName']

    SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
    print(SNS_TOPIC_ARN)

    execution_arn = event['param']['Tags']['AWS_STEP_FUNCTIONS_EXECUTION_ARN']
    region = execution_arn.split(':')[3]
    workflow_link = f'https://{region}.console.aws.amazon.com/states/home?region={region}#/executions/details/{execution_arn}'

    message = f'''message:

{status} - {job_name}
{workflow_link}
'''

    publish_message(SNS_TOPIC_ARN, message, status)
    
    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }

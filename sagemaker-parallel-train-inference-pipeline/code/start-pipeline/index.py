import yaml
import boto3
import json
from datetime import datetime
from dateutil import tz
import os
import urllib
import uuid

sns_client = boto3.client('sns')
sfn_client = boto3.client('stepfunctions')
ecr_client = boto3.client('ecr')
jmespath_expression = 'sort_by(imageDetails, &to_string(imagePushedAt))[-1].imageTags'
client_paginator = ecr_client.get_paginator('describe_images')
JST = tz.gettz('Asia/Tokyo')

STEPFUNCTION_ARN = os.environ['STEPFUNCTION_ARN']
ECR_PREP_REPO_URI = os.environ['ECR_PREP_REPO_URI']
ECR_TRAIN_REPO_URI = os.environ['ECR_TRAIN_REPO_URI']
BUCKET_NAME = os.environ['BUCKET_NAME']
PREFIX = os.environ['PREFIX']


def get_latest_image_uri(repo_uri):
    repo_name = repo_uri.split('/')[-1]
    iterator = client_paginator.paginate(repositoryName=repo_name)
    filter_iterator = iterator.search(jmespath_expression)
    tag = list(filter_iterator)[0]
    latest_image_uri = f'{repo_uri}:{tag}'
    return latest_image_uri


def publish_message(sns_topic_arn, message):
    response = sns_client.publish(
        TopicArn=sns_topic_arn,
        Message=message,
        Subject=f"ML Pipeline Started."
    )

    return response


def lambda_handler(event, context):
    print(event)
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    num_of_segment = 2
    sfn_timestamp = datetime.now(JST).strftime('%Y%m%d')
    job_name_prefix = 'ml-' + sfn_timestamp + '-' + str(uuid.uuid4())
    data_timestamp = datetime.now(JST).strftime('%Y%m')
    prep_job_name = job_name_prefix + '-prep'
    train_job_name = job_name_prefix + '-train'
    pred_job_name = job_name_prefix + '-pred'
    post_job_name = job_name_prefix + '-post'

    raw_data_key = os.path.dirname(key)
    raw_data_s3_path = f's3://{bucket}/{raw_data_key}'
    prep_output_data = f's3://{BUCKET_NAME}/{PREFIX}/prep/{prep_job_name}'
    train_output_data = f's3://{BUCKET_NAME}/{PREFIX}/train/{train_job_name}'
    pred_output_data = f's3://{BUCKET_NAME}/{PREFIX}/pred/{pred_job_name}'
    post_output_data = f's3://{BUCKET_NAME}/{PREFIX}/post/{post_job_name}'

    pred_args = [
            '--num-of-dataset', str(num_of_segment),
            '--metrics-threshold', '10000',
            '--latest-model-path', train_output_data,
            '--previous-model-path', train_output_data
        ]

    sfn_input = {
        "TimeStamp": data_timestamp,
        "PrepJobName": prep_job_name,
        "PrepInput": raw_data_s3_path,
        "PrepOutput": prep_output_data,
        "TrainJobName": train_job_name,
        "TrainInput": prep_output_data + '/train',
        "TrainOutput": train_output_data,
        "PredJobName": pred_job_name,
        "PredArgs": pred_args,
        "PredInput": prep_output_data + '/pred',
        "PredOutput": pred_output_data,
        "PostJobName": post_job_name,
        "PostInput": pred_output_data,
        "PostOutput": post_output_data,
    }

    response = sfn_client.start_execution(
        stateMachineArn=STEPFUNCTION_ARN,
        input=json.dumps(sfn_input)
    )
    print(response)

    SNS_TOPIC_ARN = os.environ['SNS_TOPIC_ARN']
    print(SNS_TOPIC_ARN)

    region = STEPFUNCTION_ARN.split(':')[3]
    execution_arn = response['executionArn']
    workflow_link = f'https://{region}.console.aws.amazon.com/states/home?region={region}#/executions/details/{execution_arn}'
    
    message = f'''message: Pipeline Started.
    {workflow_link}'''

    publish_message(SNS_TOPIC_ARN, message)

    return {
        'statusCode': 200,
        'body': json.dumps('Hello from Lambda!')
    }

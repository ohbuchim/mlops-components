import boto3
import logging
import os
import time
import yaml

import sagemaker
from sagemaker.processing import Processor
from sagemaker.processing import ProcessingInput, ProcessingOutput

import stepfunctions
from stepfunctions.inputs import ExecutionInput
from stepfunctions.workflow import Workflow
from stepfunctions.steps.states import Retry
from stepfunctions.steps import (
    Chain,
    ProcessingStep,
)

stepfunctions.set_stream_logger(level=logging.INFO)
config_name = 'pipeline-config.yml'

REGION = os.environ['REGION']
ACCOUNT_ID = os.environ['ACCOUNT_ID']
EXEC_ID = os.environ['EXEC_ID']

lambda_client = boto3.client('lambda', region_name=REGION)
ecr_client = boto3.client('ecr', region_name=REGION)
sagemaker_session = sagemaker.Session()


def get_parameters():
    params = {}
    with open(config_name) as file:
        config = yaml.safe_load(file)
        params['bucket-name'] = config['config']['bucket-name']
        params['s3-prefix'] = config['config']['s3-prefix']
        params['sagemaker-role'] = config['config']['sagemaker-role']
        params['sfn-workflow-arn'] = config['config']['sfn-workflow-arn']
        params['sfn-role-arn'] = config['config']['sfn-role-arn']
        params['prep-image-name'] = config['config']['prep-image-name']
        params['train-image-name'] = config['config']['train-image-name']
        params['notification-lambda-name'] = config['config']['notification-lambda-name']
        params['startsfn-lambda-name'] = config['config']['startsfn-lambda-name']
        params['startsfn-lambda-role-arn'] = config['config']['startsfn-lambda-role-arn']
        params['sns-topic-arn'] = config['config']['sns-topic-arn']
        params['num-of-segment'] = config['config']['num-of-segment']
        params['metric-threshold'] = config['config']['metric-threshold']

        print('------------------')
        print(params)
    return params


def get_latest_image_uri(repo_name):
    jmespath_expression = 'sort_by(imageDetails, &to_string(imagePushedAt))[-1].imageTags'
    client_paginator = ecr_client.get_paginator('describe_images')
    iterator = client_paginator.paginate(repositoryName=repo_name)
    filter_iterator = iterator.search(jmespath_expression)
    tag = list(filter_iterator)[0]
    repo_uri = f'{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/{repo_name}'
    latest_image_uri = f'{repo_uri}:{tag}'
    return latest_image_uri


def create_prep_processing(params, sagemaker_role):

    prep_processor = Processor(
        role=sagemaker_role,
        image_uri=get_latest_image_uri(params['prep-image-name']),
        instance_count=1, 
        instance_type="ml.m5.xlarge",
        volume_size_in_gb=16,
        volume_kms_key=None,
        output_kms_key=None,
        max_runtime_in_seconds=86400,  # default is 24 hours(60*60*24)
        sagemaker_session=None,
        env=None,
        network_config=None
    )
    return prep_processor


def function_exists(function_name):
    lambda_client = boto3.client('lambda')
    try:
        lambda_client.get_function(
            FunctionName=function_name,
        )
        return True
    except Exception as e:
        return False


def create_lambda_function(function_name, file_name, role_arn, handler_name,
                           envs={}, py_version='python3.9'):

    with open(file_name+'.zip', 'rb') as f:
        zip_data = f.read()

    if function_exists(function_name):

        response = lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={
                'Variables': envs
            },
        )
        time.sleep(10)
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_data,
            Publish=True,
        )

    else:
        response = lambda_client.create_function(
            FunctionName=function_name,
            Role=role_arn,
            Handler=handler_name+'.lambda_handler',
            Runtime=py_version,
            Code={
                'ZipFile': zip_data
            },
            Environment={
                'Variables': envs
            },
            Timeout=60*5,  # 5 minutes
            MemorySize=128,  # 128 MB
            Publish=True,
            PackageType='Zip',
        )
    return response['FunctionArn']


def create_prep_step(params, prep_processor, execution_input):
    code_path = '/opt/ml/processing/input/code'
    input_dir = '/opt/ml/processing/input/data'
    output_dir = '/opt/ml/processing/output'

    SCRIPT_LOCATION = "code/sagemaker/prep"

    code_s3_path = sagemaker_session.upload_data(
        SCRIPT_LOCATION,
        bucket=params['bucket-name'],
        key_prefix=os.path.join(params['s3-prefix'], SCRIPT_LOCATION, EXEC_ID),
    )

    prep_inputs = [
        ProcessingInput(
            input_name='code',
            source=code_s3_path,
            destination=code_path),
        ProcessingInput(
            source=execution_input["PrepInput"],
            destination=input_dir,
            input_name="data"
        )
    ]

    prep_outputs = [
        ProcessingOutput(
            source=output_dir,
            destination=execution_input["PrepOutput"],
            output_name="result",
        )
    ]

    prep_step = ProcessingStep(
        'Data Preparation',
        processor=prep_processor,
        job_name=execution_input['PrepJobName'],
        inputs=prep_inputs,
        outputs=prep_outputs,
        container_arguments=['--num-of-dataset',
                             str(params['num-of-segment'])],
        container_entrypoint=["python3",
                              "/opt/ml/processing/input/code/prep.py"],
        wait_for_completion=True,
        tags={'EXEC_ID': EXEC_ID}
    )

    return prep_step


def create_train_processing(params, sagemaker_role):

    train_processor = Processor(
        role=sagemaker_role,
        image_uri=get_latest_image_uri(params['train-image-name']),
        instance_count=params['num-of-segment'],
        instance_type="ml.m5.xlarge",
        volume_size_in_gb=16,
        volume_kms_key=None,
        output_kms_key=None,
        max_runtime_in_seconds=86400,  # default is 24 hours(60*60*24)
        sagemaker_session=None,
        env=None,
        network_config=None
    )

    return train_processor


def create_training_step(params, train_processor, execution_input):
    code_path = '/opt/ml/processing/input/code'
    input_dir = '/opt/ml/processing/input/data'
    output_dir = '/opt/ml/processing/output'

    SCRIPT_LOCATION = "code/sagemaker/train"

    code_s3_path = sagemaker_session.upload_data(
        SCRIPT_LOCATION,
        bucket=params['bucket-name'],
        key_prefix=os.path.join(params['s3-prefix'], SCRIPT_LOCATION, EXEC_ID),
    )

    train_inputs = [
        ProcessingInput(
            input_name='code',
            source=code_s3_path,
            destination=code_path),
        ProcessingInput(
            source=execution_input["TrainInput"],
            destination=input_dir,
            input_name="data",
            s3_data_distribution_type='ShardedByS3Key'
        )
    ]

    train_outputs = [
        ProcessingOutput(
            source=output_dir,
            destination=execution_input["TrainOutput"],
            output_name="result",
        )
    ]

    train_step = ProcessingStep(
        "Model Training",
        processor=train_processor,
        job_name=execution_input["TrainJobName"],
        inputs=train_inputs,
        outputs=train_outputs,
        container_arguments=['--num-of-dataset',
                             str(params['num-of-segment'])],
        container_entrypoint=["python3",
                              "/opt/ml/processing/input/code/train.py"],
        wait_for_completion=True,
        tags={'EXEC_ID': EXEC_ID}
    )

    return train_step


def create_pred_processor(params, sagemaker_role):
    pred_processor = Processor(
        role=sagemaker_role,
        image_uri=get_latest_image_uri(params['train-image-name']),
        instance_count=params['num-of-segment'],
        instance_type="ml.m5.xlarge",
        volume_size_in_gb=16,
        volume_kms_key=None,
        output_kms_key=None,
        max_runtime_in_seconds=86400,  # default is 24 hours(60*60*24)
        sagemaker_session=None,
        env=None,
        network_config=None
    )

    return pred_processor


def create_pred_step(params, pred_processor, execution_input):
    code_path = '/opt/ml/processing/input/code'
    input_dir = '/opt/ml/processing/input/data'
    output_dir = '/opt/ml/processing/output'

    SCRIPT_LOCATION = "code/sagemaker/pred"

    code_s3_path = sagemaker_session.upload_data(
        SCRIPT_LOCATION,
        bucket=params['bucket-name'],
        key_prefix=os.path.join(params['s3-prefix'], SCRIPT_LOCATION, EXEC_ID),
    )

    pred_inputs = [
        ProcessingInput(
            input_name='code',
            source=code_s3_path,
            destination=code_path),
        ProcessingInput(
            source=execution_input["PredInput"],
            destination=input_dir,
            input_name="data",
            s3_data_distribution_type='ShardedByS3Key'
        )
    ]

    pred_outputs = [
        ProcessingOutput(
            source=output_dir,
            destination=execution_input["PredOutput"],
            output_name="result",
        )
    ]

    pred_step = ProcessingStep(
        "Batch Inference",
        processor=pred_processor,
        job_name=execution_input["PredJobName"],
        inputs=pred_inputs,
        outputs=pred_outputs,
        container_arguments=execution_input["PredArgs"],
        container_entrypoint=["python3",
                              "/opt/ml/processing/input/code/pred.py"],
        wait_for_completion=True,
        tags={'EXEC_ID': EXEC_ID}
    )

    return pred_step


def create_post_processor(params, sagemaker_role):
    post_processor = Processor(
        role=sagemaker_role,
        image_uri=get_latest_image_uri(params['prep-image-name']),
        instance_count=1, 
        instance_type="ml.m5.xlarge",
        volume_size_in_gb=16,
        volume_kms_key=None,
        output_kms_key=None,
        max_runtime_in_seconds=86400,  # default is 24 hours(60*60*24)
        sagemaker_session=None,
        env=None,
        network_config=None
    )

    return post_processor


def create_post_step(params, post_processor, execution_input):
    code_path = '/opt/ml/processing/input/code'
    input_dir = '/opt/ml/processing/input/data'
    output_dir = '/opt/ml/processing/output'

    SCRIPT_LOCATION = "code/sagemaker/post"

    code_s3_path = sagemaker_session.upload_data(
        SCRIPT_LOCATION,
        bucket=params['bucket-name'],
        key_prefix=os.path.join(params['s3-prefix'], SCRIPT_LOCATION, EXEC_ID),
    )

    post_inputs = [
        ProcessingInput(
            input_name='code',
            source=code_s3_path,
            destination=code_path),
        ProcessingInput(
            source=execution_input["PostInput"],
            destination=input_dir,
            input_name="data"
        )
    ]

    post_outputs = [
        ProcessingOutput(
            source=output_dir,
            destination=execution_input["PostOutput"],
            output_name="result",
        )
    ]

    post_step = ProcessingStep(
        "Post Process",
        processor=post_processor,
        job_name=execution_input["PostJobName"],
        inputs=post_inputs,
        outputs=post_outputs,
        container_arguments=[
            '--num-of-dataset', str(params['num-of-segment'])
        ],
        container_entrypoint=["python3",
                              "/opt/ml/processing/input/code/post.py"],
        wait_for_completion=True,
        tags={'EXEC_ID': EXEC_ID}
    )

    return post_step


def create_notification_step(lambda_function_name, id, message):

    lambda_step = stepfunctions.steps.compute.LambdaStep(
        id,
        parameters={
            "FunctionName": lambda_function_name,
            "Payload": {
                "status": message,
                "param.$": "$"
            },
        },
    )
    lambda_step.add_retry(
        Retry(error_equals=["States.TaskFailed"], interval_seconds=15,
              max_attempts=2, backoff_rate=4.0)
    )
    return lambda_step


def create_sfn_workflow(params):
    sfn_workflow_name = params['sfn-workflow-arn'].split(':')[-1]
    workflow_execution_role = params['sfn-role-arn']

    failed_state = stepfunctions.steps.states.Fail(
        "ML Workflow failed", cause="SageMakerJobFailed"
    )

    sns_step = stepfunctions.steps.service.SnsPublishStep(
        "Error Message",
        comment="error",
        parameters={
            "TopicArn": params['sns-topic-arn'],
            "Message.$": "$",
            "Subject": f"Workflow Error: {sfn_workflow_name}"
        }
    )
    sns_step.next(failed_state)

    catch_state = stepfunctions.steps.states.Catch(
        error_equals=["States.ALL"],
        next_step=sns_step,
    )

    prep_processor = create_prep_processing(params,
                                            params['sagemaker-role'])
    prep_step = create_prep_step(params,
                                 prep_processor, execution_input)

    train_processor = create_train_processing(params, params['sagemaker-role'])
    train_step = create_training_step(params, train_processor, execution_input)

    pred_processor = create_pred_processor(params,
                                           params['sagemaker-role'])
    pred_step = create_pred_step(params, pred_processor,
                                 execution_input)

    post_processor = create_post_processor(params,
                                           params['sagemaker-role'])
    post_step = create_post_step(params, post_processor,
                                 execution_input)

    train_notification_step = create_notification_step(
                                    params['notification-lambda-name'],
                                    'Train Notification',
                                    'Training Completed.')
    post_notification_step = create_notification_step(
                                    params['notification-lambda-name'],
                                    'Postprocess Notification',
                                    'Postprocess Completed.')

    prep_step.add_catch(catch_state)
    train_step.add_catch(catch_state)
    pred_step.add_catch(catch_state)
    post_step.add_catch(catch_state)

    workflow_graph = Chain([
                        prep_step,
                        train_step,
                        train_notification_step,
                        pred_step,
                        post_step,
                        post_notification_step])

    branching_workflow = Workflow(
        name=sfn_workflow_name,
        definition=workflow_graph,
        role=workflow_execution_role,
    )

    branching_workflow.create()
    branching_workflow.update(workflow_graph)

    time.sleep(5)

    return branching_workflow


if __name__ == '__main__':
    params = get_parameters()

    execution_input = ExecutionInput(
        schema={
            "TimeStamp": str,
            "PrepJobName": str,
            "PrepInput": str,
            "PrepOutput": str,
            "TrainJobName": str,
            "TrainInput": str,
            "TrainOutput": str,
            "PredJobName": str,
            "PredArgs": str,
            "PredInput": str,
            "PredOutput": str,
            "PostJobName": str,
            "PostInput": str,
            "PostOutput": str,
        }
    )

    envs = {
        'SNS_TOPIC_ARN': params['sns-topic-arn'],
        'STEPFUNCTION_ARN': params['sfn-workflow-arn'],
        'BUCKET_NAME': params['bucket-name'],
        'PREFIX': params['s3-prefix'],
        'NUM_OF_SEGMENT': str(params['num-of-segment']),
        'METRIC_THRESHOLD': str(params['metric-threshold'])
    }
    lambda_startsfn_function_arn = create_lambda_function(
                                    params['startsfn-lambda-name'],
                                    params['startsfn-lambda-name'],
                                    params['startsfn-lambda-role-arn'],
                                    'index',
                                    envs,
                                    py_version='python3.8')
    print(f'{lambda_startsfn_function_arn} has been updated.')

    branching_workflow = create_sfn_workflow(params)

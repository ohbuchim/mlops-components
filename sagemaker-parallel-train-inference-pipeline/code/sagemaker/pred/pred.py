import argparse
import boto3
import json
import os
import pandas as pd
from pprint import pprint
import shutil
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
import torch
import yaml
from autogluon.tabular import TabularDataset, TabularPredictor

s3_client = boto3.client('s3')
s3 = boto3.resource('s3')


def get_input_path(path):
    file = os.listdir(path)[0]
    if len(os.listdir(path)) > 1:
        print("WARN: more than one file is found in this directory")
    print(f"Using {file}")
    filename = f"{path}/{file}"
    return filename


def get_env_if_present(name):
    result = None
    if name in os.environ:
        result = os.environ[name]
    return result


def latest_model_is_best(latest_model_path, num_of_dataset, thresh):
    result = True
    bucket_name = latest_model_path.split('/')[2]
    latest_model_prefix = latest_model_path[6+len(bucket_name):]

    # ひとつでも評価値が閾値よりも低い場合は古いモデルを使う
    for i in range(num_of_dataset):
        model_id = str(i).zfill(2)
        response = s3_client.get_object(
                            Bucket=bucket_name,
                            Key=os.path.join(latest_model_prefix, model_id, 'eval.yml'))
        eval_dict = yaml.safe_load(response['Body'].read().decode('utf-8'))
        print(f'MAE of model {model_id} is', eval_dict['MAE'], ', thresh is', thresh)
        if eval_dict['MAE'] > thresh:
            print('MAE', eval_dict['MAE'], 'is worse than thresh', thresh)
            result = False
            break

    return result


def get_pretrained_model(model_id, latest_model_path,
                         previous_model_path, thresh,
                         num_of_dataset,
                         model_path
                         ):
    bucket_name = latest_model_path.split('/')[2]
    latest_model_prefix = latest_model_path[6+len(bucket_name):]
    previous_model_prefix = previous_model_path[6+len(bucket_name):]

    if latest_model_is_best(latest_model_path, num_of_dataset, thresh):
        prefix = latest_model_prefix
        print(f'The latest models are used: {prefix}/{model_id}')
    else:
        prefix = previous_model_prefix
        print(f'The previous models are used: {prefix}/{model_id}')

    # モデル単位で評価値を判定する場合
    # 最新モデルの評価値が閾値よりもよければ最新モデルを使ってバッチ推論
    # そうでなければ以前のモデルを使ってバッチ推論
    # response = s3_client.get_object(
    #                         Bucket=bucket_name,
    #                         Key=os.path.join(latest_model_prefix, model_id, 'eval.yml'))
    # eval_dict = yaml.safe_load(response['Body'].read().decode('utf-8'))

    # print('MAE:', eval_dict['MAE'], 'Threshold:', thresh)
    # if eval_dict['MAE'] < thresh:
    #     print('The latest models are used.')
    #     prefix = latest_model_prefix
    # else:
    #     print('The previous models are used.')
    #     prefix = previous_model_prefix
    model_download_path = os.path.join(model_path, 'model.zip')
    s3.meta.client.download_file(bucket_name,
                                 os.path.join(prefix, model_id, 'model.zip'),
                                 model_download_path
                                 )
    shutil.unpack_archive(model_download_path, model_path)
    return prefix


if __name__ == "__main__":
    # Disable Autotune
    os.environ["MXNET_CUDNN_AUTOTUNE_DEFAULT"] = "0"

    parser = argparse.ArgumentParser()

    # Data and model checkpoints directories
    parser.add_argument('--num-of-dataset', type=int, default=1, metavar='N',
                        help='N of dataset')
    parser.add_argument('--metrics-threshold', type=float, default=1, metavar='N',
                        help='metrics-threshold')
    parser.add_argument('--latest-model-path', type=str, default='', metavar='N',
                        help='latest-model-path')
    parser.add_argument('--previous-model-path', type=str, default='', metavar='N',
                        help='previous-model-path')
    args = parser.parse_args()

    # 複数インスタンスを使用した場合に、自分がどのインスタンス（ID）なのかを取得
    with open('/opt/ml/config/resourceconfig.json') as f:
        host_settings = json.load(f)
        current_host = host_settings['current_host']
        print('current_host:', current_host)

    # run 実行時に入出力として指定されたパスを取得
    with open('/opt/ml/config/processingjobconfig.json') as f:
        processingjobconfig = json.load(f)
        print('processingjobconfig', processingjobconfig)
        output_data_path = ''
        outputs = processingjobconfig['ProcessingOutputConfig']['Outputs']
        for o in outputs:
            if o['OutputName'] == 'result':
                output_data_path = o['S3Output']['LocalPath']

        inputs = processingjobconfig['ProcessingInputs']
        code_path = ''
        input_data_path = ''
        for i in inputs:
            if i['InputName'] == 'code':
                code_path = i['S3Input']['LocalPath']
            elif i['InputName'] == 'data':
                input_data_path = i['S3Input']['LocalPath']

    pred_file = get_input_path(input_data_path)
    pred_df = pd.read_csv(pred_file)

    model_path = '/opt/ml/processing/input/model'
    os.makedirs(model_path)
    model_id = pred_file.split('_')[-1].split('.')[0]
    model_prefix = get_pretrained_model(
            model_id,
            args.latest_model_path,
            args.previous_model_path,
            args.metrics_threshold,
            args.num_of_dataset,
            model_path
    )

    with open(os.path.join(output_data_path, f'{model_id}.log'), 'w') as f:
        f.write(model_prefix)

    predictor = TabularPredictor.load(model_path)

    result = predictor.predict(pred_df.drop(columns=['medianHouseValue']))
    result.to_csv(os.path.join(output_data_path, f'result_{model_id}.csv'), index=None)

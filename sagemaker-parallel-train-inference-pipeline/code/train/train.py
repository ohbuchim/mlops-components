import argparse
import json
import os
import pandas as pd
from pprint import pprint
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split
import torch
import shutil
import yaml
from autogluon.tabular import TabularDataset, TabularPredictor


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


if __name__ == "__main__":
    # Disable Autotune
    os.environ["MXNET_CUDNN_AUTOTUNE_DEFAULT"] = "0"
    n_gpus = torch.cuda.device_count()

    parser = argparse.ArgumentParser()

    # Data and model checkpoints directories
    parser.add_argument('--num-of-dataset', type=int, default=1, metavar='N',
                        help='N of dataset')
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

    config_file = os.path.join(code_path, 'config.yml')
    with open(config_file) as f:
        config = yaml.safe_load(f)  # AutoGluon-specific config

    if n_gpus:
        config["num_gpus"] = int(args.n_gpus)

    print("Running training job with the config:")
    pprint(config)

    train_file = get_input_path(input_data_path)
    input_df = pd.read_csv(train_file)
    train_df, test_df = train_test_split(
        input_df, test_size=0.2, random_state=0
    )
    train_data = TabularDataset(train_df)

    model_id = train_file.split('_')[-1].split('.')[0]

    os.makedirs('/opt/ml/processing/tmp')
    ag_predictor_args = config["ag_predictor_args"]
    ag_predictor_args["path"] = '/opt/ml/processing/tmp'
    ag_fit_args = config["ag_fit_args"]

    predictor = TabularPredictor(**ag_predictor_args).fit(train_data, **ag_fit_args)

    result = predictor.predict(test_df.drop(columns=['medianHouseValue']))
    mae = mean_absolute_error(test_df['medianHouseValue'], result)

    eval_file = os.path.join(output_data_path, model_id, 'eval.yml')
    os.makedirs(os.path.join(output_data_path, model_id))
    with open(eval_file, 'w') as f:
        yaml.dump({'MAE': float(mae)}, f)

    # あとで S3 からダウンロードしやすいよう ZIP で圧縮
    shutil.make_archive(os.path.join(output_data_path, model_id, 'model'), format='zip', root_dir='/opt/ml/processing/tmp')

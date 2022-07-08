import argparse
import json
import logging
import os
import pandas as pd
from sklearn.model_selection import train_test_split
import sys
import glob

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler(sys.stdout))


if __name__ == '__main__':
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

    input_files = glob.glob(f"{input_data_path}/*")
    print('input:', str(len(input_files)), input_files[:100])
    print('code:', glob.glob(f"{code_path}/*"))

    log_file = os.path.join(output_data_path, current_host+'.txt')
    with open(log_file, 'w') as f:
        f.write('\n'.join(input_files))

    num_of_dataset = int(args.num_of_dataset)
    rawdata_path = os.path.join(input_data_path, 'rawdata.csv')
    rawdata_df = pd.read_csv(rawdata_path)

    train_df, test_df = train_test_split(
        rawdata_df, test_size=0.2, random_state=0
    )
    os.makedirs(os.path.join(output_data_path, 'train'))
    os.makedirs(os.path.join(output_data_path, 'pred'))
    for n in range(num_of_dataset):
        idx = str(n).zfill(2)
        os.makedirs(os.path.join(output_data_path, 'train', idx))
        train_df.to_csv(os.path.join(output_data_path, 'train', f'train_{idx}.csv'), index=None)
        test_df.to_csv(os.path.join(output_data_path, 'pred', f'pred_{idx}.csv'), index=None)

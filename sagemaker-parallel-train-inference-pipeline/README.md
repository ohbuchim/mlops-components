# AutoGluon 並列モデル学習とバッチ推論パイプライン

このサンプルを使って、S3 バケットへのファイルアップロードをトリガーとして実行されるバッチ推論パイプラインを作成することができます。

<img src="workflow.png" width="50%">

Raw Data 保存用 S3 バケットの、Raw Data と同じフォルダに拡張子が .run のファイルがアップロードされると、それをトリガーに Lambda 関数が実行され、そこから Step Functions Workflow が実行されます。Step Functions Workflow では、SageMaker Processing を使ってデータの準備、モデルの学習（並列）、バッチ推論（並列）、後処理が順に実行されます。モデルの学習は AutoGluon-Tabular を使用しており、また、モデルの学習が終わった後に評価用データを使ってモデルの評価値（MAE）を算出してファイルに出力しています。バッチ推論スクリプトの中では、前段で学習したモデルの評価値を読み出し、いずれかひとつのモデルの評価値が閾値よりも大きい（性能が良くない）場合は、前段で学習したモデルではなくあらかじめ指定してあるデフォルトモデルを使用して推論を行なっています。Step Functions Workflow 開始時、モデル学習完了時、後処理完了時に Amazon SNS 経由でメールが送信されます。

<img src="workflow2.png" width="50%">

## 前提条件

このサンプルは、Amazon SageMaker ノートブックインスタンスでの動作を確認しています。ノートブックインスタンスタイプは t3.medium でも動作しますが、コンテナイメージのビルド時間を短縮したい場合は m5.xlarge をご利用ください。コンテナイメージのビルドと Amazon ECR への push に t3.medium だと 20 分程度、m5.xlarge だと 10 分程度かかります。

## 使用する主なサービス

- Amazon SageMaker
- AWS Step Functions
- AWS Lambda
- Amazon SNS
- Amazon ECR
- AWS CodePipeline
- AWS CodeBuild
- AWS CodeCommit

## ファイル構成

```
root
├── code/                  // SageMaker や Lambda で使用するコード
├── docker/                // SageMaker が利用するコンテナイメージ関連ファイル
├── policy/                // 各種リソースで使用する IAM Policy の JSON
├── repo/                  // CodeBuild で使用するファイル一式
├── 00-prepare-container-images.ipynb    // コンテナイメージ作成用ノートブック
├── 01-sagemaker-training-inference-pipeline.ipynb    // ML パイプライン作成用ノートブック
├── 02-create-ml-pipeline-using-codepipeline.ipynb    // ML パイプライン更新パイプライン作成用ノートブック
```

ノートブックは、以下の順番で実行してください。

1. 00-prepare-container-images.ipynb
2. 01-sagemaker-training-inference-pipeline.ipynb
3. 02-create-ml-pipeline-using-codepipeline.ipynb

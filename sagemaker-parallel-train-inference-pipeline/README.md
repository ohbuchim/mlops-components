# AutoGluon 並列モデル学習とバッチ推論パイプライン

このサンプルを使って、S3 バケットへのファイルアップロードをトリガーとして実行されるバッチ推論パイプラインを作成することができます。データセットの数だけ SageMaker 学習用インスタンスを起動し、それぞれのインスタンスで個別にモデルの学習を実行します。データセットの数と同じ数のモデルができるので、バッチ推論も同じ数のインスタンスを使って並列で実行します。

<img src="workflow.png" width="50%">

## ファイル構成

```
root
├── code/                  // SageMaker や Lambda で使用するコード
├── docker/                // SageMaker が利用するコンテナイメージ関連ファイル
├── policy/                // 各種リソースで使用する IAM Policy の JSON
├── 00-prepare-container-images.ipynb    // コンテナイメージ作成用ノートブック
├── 01-sagemaker-training-inference-pipeline.ipynb    // ML パイプライン作成用ノートブック

```

## 前提条件

このサンプルは、Amazon SageMaker ノートブックインスタンスでの動作を確認しています。ノートブックインスタンスタイプは t3.medium でも動作しますが、コンテナイメージのビルド時間を短縮したい場合は m5.xlarge をご利用ください。コンテナイメージのビルドと Amazon ECR への push に t3.medium だと 20分程度、m5.xlarge だと 10分程度かかります。

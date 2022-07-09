REGION=${AWS_DEFAULT_REGION}
REGISTRY_URL="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com" 
# IMAGE_TAG="$(git rev-parse HEAD)"
# IMAGE_TAG="$(git rev-parse --short HEAD)"

echo "========"
echo EXEC_ID: ${EXEC_ID}
echo "========"
echo REGION: ${REGION}

IMAGE_TAG=${EXEC_ID}

# docker 関連ファイルの変更がない場合はビルドはスキップ
# pipeline.py の中で SageMaker は最新のイメージを使用する
TARGET=$(git log -n 1 --name-only  | grep -e "docker/")
if [ -z "$TARGET" ]; then
  echo "=== No updates for container images. ==="
  exit 0
fi

# prep
ECR_REPOGITORY=${PREP_REPO_NAME}
IMAGE_URI="${REGISTRY_URL}/${ECR_REPOGITORY}"
PREPRO_IMAGE_URI=$IMAGE_URI:$IMAGE_TAG

aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY_URL
aws ecr create-repository --repository-name $ECR_REPOGITORY

docker build -t $ECR_REPOGITORY docker/prep/
docker tag ${ECR_REPOGITORY} $IMAGE_URI:${IMAGE_TAG}
docker push $IMAGE_URI:${IMAGE_TAG}

echo "Container registered. URI:${IMAGE_URI}"

# train
ECR_REPOGITORY=${TRAIN_REPO_NAME}
IMAGE_URI="${REGISTRY_URL}/${ECR_REPOGITORY}"
TRAIN_IMAGE_URI=$IMAGE_URI:$IMAGE_TAG

aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin 763104351884.dkr.ecr.${REGION}.amazonaws.com
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY_URL
aws ecr create-repository --repository-name $ECR_REPOGITORY

docker build -t $ECR_REPOGITORY docker/train/
docker tag ${ECR_REPOGITORY} $IMAGE_URI:${IMAGE_TAG}
docker push $IMAGE_URI:${IMAGE_TAG}

echo "Container registered. URI:${IMAGE_URI}"

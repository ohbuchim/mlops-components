ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
REGION=$(python setenv.py config region)
TIMESTAMP=$(TZ='Asia/Tokyo' date '+%Y%m%d%H%M')
EXEC_ID=${EXEC_ID}
PREP_REPO_NAME=$(python setenv.py config prep-image-name)
TRAIN_REPO_NAME=$(python setenv.py config train-image-name)
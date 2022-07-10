LAMBDA_FUNC_NAME=$(python setenv.py config startsfn-lambda-name)
rm -rf ${LAMBDA_FUNC_NAME}
rm ${LAMBDA_FUNC_NAME}.zip
mkdir ${LAMBDA_FUNC_NAME}
pip install pyyaml -t ${LAMBDA_FUNC_NAME}
cp code/lambda/start-pipeline/index.py ${LAMBDA_FUNC_NAME}
cd ${LAMBDA_FUNC_NAME}
zip -r ../${LAMBDA_FUNC_NAME}.zip .
cd ..

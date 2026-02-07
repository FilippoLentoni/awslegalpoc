#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="awslegalpoc-streamlit"
AWS_REGION="${AWS_REGION:-$(aws configure get region)}"

if [[ -z "${AWS_REGION}" ]]; then
  echo "AWS region not set. Export AWS_REGION or configure a default region."
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

if ! aws ecr describe-repositories --repository-names "${REPO_NAME}" --region "${AWS_REGION}" >/dev/null 2>&1; then
  echo "ECR repo ${REPO_NAME} not found. Create it by running:"
  echo "  (cd infra && cdk deploy AwsLegalPocEcrStack --require-approval never)"
  exit 1
fi

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

DOCKER_CMD="${DOCKER_CMD:-docker}"
if ! ${DOCKER_CMD} info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    DOCKER_CMD="sudo docker"
  fi
fi

aws ecr get-login-password --region "${AWS_REGION}" | ${DOCKER_CMD} login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

${DOCKER_CMD} tag "${REPO_NAME}:latest" "${ECR_URI}:latest"
${DOCKER_CMD} push "${ECR_URI}:latest"

echo "Pushed: ${ECR_URI}:latest"

#!/usr/bin/env bash
set -euo pipefail

# 0) Ensure AWS credentials are available to CDK (supports aws login)
if command -v aws >/dev/null 2>&1; then
  eval "$(aws configure export-credentials --format env)" || true
  export AWS_SDK_LOAD_CONFIG=1
fi

# 1) Bootstrap if needed
if [[ ! -d "infra/.venv" ]]; then
  python3.11 -m venv infra/.venv
fi
infra/.venv/bin/pip install -r infra/requirements.txt

(cd infra && cdk bootstrap)

# 2) Build docker image
./scripts/build.sh

# 3) Push to ECR
./scripts/push.sh

# 4) Deploy infra stacks
(cd infra && cdk deploy AwsLegalPocAgentCoreStack --require-approval never)
(cd infra && cdk deploy AwsLegalPocAppStack --require-approval never)

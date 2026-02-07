#!/usr/bin/env bash
set -euo pipefail

# Ensure AWS credentials are available to CDK (supports aws login)
if command -v aws >/dev/null 2>&1; then
  eval "$(aws configure export-credentials --format env)" || true
  export AWS_SDK_LOAD_CONFIG=1
fi

if [[ ! -d "infra/.venv" ]]; then
  python3.11 -m venv infra/.venv
fi
infra/.venv/bin/pip install -r infra/requirements.txt

(cd infra && cdk destroy --force)

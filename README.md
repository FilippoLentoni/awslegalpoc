# awslegalpoc

Streamlit-based customer support chatbot using AgentCore + Strands + RAG, deployable to ECS Fargate behind ALB + Cognito.

## Repo Structure

- `app/` Streamlit UI
- `core/` Agent logic, tools, RAG, Langfuse integration
- `infra/` AWS CDK app (ECR, ECS, ALB, Cognito)
- `scripts/` Build/push/deploy helpers
- `resources/` External references (gitignored)

## Prerequisites

- AWS CLI configured with a default region
- Docker
- AWS CDK CLI (`npm i -g aws-cdk`)
- Python 3.11 + Poetry

## Local Dev

1. Create `.env` from `.env.example` and fill in values.
2. Install deps:

```bash
/home/ec2-user/.local/bin/poetry install
```

3. Run Streamlit:

```bash
./scripts/run_local.sh
```

## Deploy (Temporary HTTP + In-App Cognito)

Optional overrides:

```bash
export BEDROCK_REGION="us-west-2"
export BEDROCK_MODEL_ID="amazon.nova-2-lite-v1:0"
export BEDROCK_INFERENCE_PROFILE_ARN="arn:aws:bedrock:us-east-1:ACCOUNT:inference-profile/global.amazon.nova-2-lite-v1:0"
export LANGFUSE_HOST="https://cloud.langfuse.com"
```

Then:

```bash
./scripts/deploy.sh
```

If the ECR repo does not exist, deploy it once:

```bash
(cd infra && cdk deploy AwsLegalPocEcrStack --require-approval never)
```

Before first run, create the temporary Cognito pool/user and config secret:

```bash
export COGNITO_USERNAME="admin"
export COGNITO_PASSWORD="ChangeMe123!"
./scripts/bootstrap_cognito.sh
```

After deploy, update the secret `awslegalpoc/langfuse` in Secrets Manager with your Langfuse keys.

## AgentCore Runtime + Gateway Deployment

1. Deploy AgentCore prerequisites (Lambda + DynamoDB + IAM):

```bash
(cd infra && cdk deploy AwsLegalPocAgentCoreStack --require-approval never)
```

2. Create memory, gateway, and runtime:

```bash
/home/ec2-user/.local/bin/poetry run python scripts/agentcore_deploy.py --wait
```

3. Seed memory + warranty data (optional but matches notebook behavior):

```bash
/home/ec2-user/.local/bin/poetry run python scripts/seed_memory.py --wait
/home/ec2-user/.local/bin/poetry run python scripts/seed_warranty_data.py
```

4. Test the runtime from EC2:

```bash
/home/ec2-user/.local/bin/poetry run python scripts/test_agentcore_runtime.py --prompt "List all of your tools"
```

## Deploy (ALB + Cognito via HTTPS later)

Set required environment variables:

```bash
export ENABLE_ALB_COGNITO="true"
export ACM_CERT_ARN="arn:aws:acm:REGION:ACCOUNT:certificate/XXXX"
export COGNITO_DOMAIN_PREFIX="awslegalpoc-<unique>"
```

## Destroy

```bash
./scripts/destroy.sh
```

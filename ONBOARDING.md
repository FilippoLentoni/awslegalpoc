# AWS Legal POC — New Customer Deployment Guide

This guide walks you through deploying the full stack into **3 brand-new AWS accounts** from scratch.
Start here after creating an EC2 instance in the orchestrator account and cloning the repo.

---

## Architecture Overview

```
GitHub (main branch)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Orchestrator Account (256455711499)                │
│  EC2 (you are here) + CodePipeline                  │
└──────────────┬──────────────────────┬───────────────┘
               │ assume role          │ assume role
               ▼                      ▼
┌──────────────────────┐   ┌──────────────────────────┐
│  Beta Account        │   │  Prod Account            │
│  ECS Fargate + ALB   │   │  ECS Fargate + ALB       │
│  Bedrock AgentCore   │   │  Bedrock AgentCore       │
│  Knowledge Base      │   │  Knowledge Base          │
│  Cognito             │   │  Cognito                 │
└──────────────────────┘   └──────────────────────────┘
```

**Pipeline flow** (triggered on every merge to `main`):

```
Source → DeployBeta → EvalTests → [Manual Approval] → DeployProd
```

---

## Prerequisites

Before starting:

1. **Three AWS accounts** — orchestrator, beta, prod — all linked to billing
2. **EC2 instance** running in the orchestrator account (Amazon Linux 2023 recommended)
3. **IAM credentials** for all 3 accounts (see Step 0)
4. **GitHub access** to the repository
5. **Langfuse account** — create a free project at https://us.cloud.langfuse.com (one project per environment is recommended)

---

## Step 0: EC2 and Credential Setup

### 0a. Install system dependencies on the EC2

SSH into your EC2 instance and run:

```bash
# System packages
sudo dnf install -y git docker

# Start Docker and add your user to the docker group
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

# ⚠️  Log out and SSH back in so the docker group takes effect
exit
```

After re-connecting:

```bash
# Node.js 18 via nvm (required for CDK)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 18
nvm use 18

# AWS CDK CLI
npm install -g aws-cdk

# Python tooling (Python 3.11 is pre-installed on AL2023)
pip install --user poetry
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 0b. Clone the repository

```bash
git clone https://github.com/FilippoLentoni/awslegalpoc.git
cd awslegalpoc
poetry install
```

### 0c. Configure AWS credentials for all 3 accounts

You need access keys for each account. Create an IAM user with `AdministratorAccess`
(or a scoped policy) in each account, download the access keys, then:

```bash
# Configure three named profiles
aws configure --profile orchestrator
# → Enter orchestrator account access key, secret, region: us-east-2

aws configure --profile beta
# → Enter beta account access key, secret, region: us-east-2

aws configure --profile prod
# → Enter prod account access key, secret, region: us-east-2

# Make orchestrator the default
aws configure
# → Enter orchestrator credentials again (same as above)
```

Verify all three work:

```bash
aws sts get-caller-identity --profile orchestrator
aws sts get-caller-identity --profile beta
aws sts get-caller-identity --profile prod
```

---

## Step 1: Update `config/environments.json`

Open [config/environments.json](config/environments.json) and replace the account IDs,
stack prefixes, and GitHub repo with your own values:

```json
{
  "github": {
    "owner": "YOUR_GITHUB_USERNAME",
    "repo": "YOUR_REPO_NAME"
  },
  "orchestrator": {
    "account": "YOUR_ORCHESTRATOR_ACCOUNT_ID",
    "region": "us-east-2",
    "stackPrefix": "orchestrator-awslegalpoc"
  },
  "beta": {
    "account": "YOUR_BETA_ACCOUNT_ID",
    "region": "us-east-2",
    "stackPrefix": "beta-awslegalpoc",
    "ecrRepository": "beta-awslegalpoc-streamlit",
    "cognitoUsername": "admin",
    "langfuseHost": "https://us.cloud.langfuse.com",
    "bedrockModelId": "amazon.nova-2-lite-v1:0",
    "bedrockInferenceProfile": "us.amazon.nova-2-lite-v1:0",
    "knowledgeBase": {
      "embeddingModel": "amazon.titan-embed-text-v2:0",
      "dimension": 1024,
      "chunkMaxTokens": 512,
      "chunkOverlapPercent": 20
    },
    "eval": {
      "dataset": "italian-legal-eval-ci",
      "judgeModel": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
      "minScore": 0.5,
      "timeout": 180
    }
  },
  "prod": {
    "account": "YOUR_PROD_ACCOUNT_ID",
    "region": "us-east-2",
    "stackPrefix": "awslegalpoc",
    "ecrRepository": "awslegalpoc-streamlit",
    "cognitoUsername": "admin",
    "langfuseHost": "https://us.cloud.langfuse.com",
    "bedrockModelId": "amazon.nova-2-lite-v1:0",
    "bedrockInferenceProfile": "us.amazon.nova-2-lite-v1:0",
    "knowledgeBase": {
      "embeddingModel": "amazon.titan-embed-text-v2:0",
      "dimension": 1024,
      "chunkMaxTokens": 512,
      "chunkOverlapPercent": 20
    },
    "eval": {
      "dataset": "italian-legal-eval-ci",
      "judgeModel": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
      "minScore": 0.5,
      "timeout": 180
    }
  }
}
```

Also delete the stale CDK AZ cache so CDK re-queries your new accounts:

```bash
rm -f cdk.context.json infra/cdk.context.json
```

Commit and push these changes to `main` before proceeding:

```bash
git add config/environments.json
git commit -m "config: update account IDs for new customer deployment"
git push origin main
```

> **GitHub push from EC2:** If you haven't set up credentials, generate an SSH key
> (`ssh-keygen -t ed25519`), add the public key to your GitHub account under
> **Settings → SSH and GPG keys**, then switch your remote:
> `git remote set-url origin git@github.com:YOUR_USERNAME/YOUR_REPO.git`

---

## Step 2: Create `config/secrets.json`

This file is gitignored and stays only on the EC2. Copy the template and fill in your values:

```bash
cp config/secrets.example.json config/secrets.json
```

Edit `config/secrets.json`:

```json
{
  "orchestrator": {
    "cognito": { "password": "" },
    "langfuse": {
      "publicKey": "pk-lf-xxxxx",
      "secretKey": "sk-lf-xxxxx"
    }
  },
  "beta": {
    "cognito": { "password": "ChooseAStrongBetaPassword1!" },
    "langfuse": {
      "publicKey": "pk-lf-xxxxx",
      "secretKey": "sk-lf-xxxxx"
    }
  },
  "prod": {
    "cognito": { "password": "ChooseAStrongProdPassword1!" },
    "langfuse": {
      "publicKey": "pk-lf-xxxxx",
      "secretKey": "sk-lf-xxxxx"
    }
  }
}
```

> Get Langfuse keys from https://us.cloud.langfuse.com → your project → **Settings → API Keys**.
> Use separate Langfuse projects for beta and prod if you want isolated traces.
>
> Cognito passwords must satisfy: min 8 chars, uppercase, lowercase, number, special character.

---

## Step 3: Enable Bedrock Model Access

Do this **in every account** (orchestrator, beta, prod) before deploying:

1. Go to **AWS Console → Amazon Bedrock → Model access** (in `us-east-2`)
2. Click **Manage model access**
3. Enable the following models:
   - **Amazon Nova Lite** (`amazon.nova-2-lite-v1:0`)
   - **Amazon Titan Embeddings V2** (`amazon.titan-embed-text-v2:0`)
   - **Anthropic Claude Sonnet** (used as eval judge — `claude-sonnet-4-5-...`)
4. Click **Save changes** and wait for status to become **Access granted**

> Model access is per-account and per-region. You must do this in all 3 accounts.

---

## Step 4: Bootstrap CDK in All 3 Accounts

CDK bootstrap creates the S3 bucket and IAM roles that CDK needs to deploy stacks.
Run once per account:

```bash
# Bootstrap orchestrator (using default profile)
cdk bootstrap aws://YOUR_ORCHESTRATOR_ACCOUNT_ID/us-east-2

# Bootstrap beta
AWS_PROFILE=beta cdk bootstrap aws://YOUR_BETA_ACCOUNT_ID/us-east-2

# Bootstrap prod
AWS_PROFILE=prod cdk bootstrap aws://YOUR_PROD_ACCOUNT_ID/us-east-2
```

Each takes about 2 minutes. You'll see `CDKToolkit` stack created in each account.

---

## Step 5: Deploy All Stacks to Beta

This single command deploys CDK infrastructure, builds and pushes the Docker image,
deploys AgentCore, and bootstraps Cognito — all in the correct order:

```bash
AWS_PROFILE=beta ./scripts/deploy-all.sh --env beta
```

**What it does (in order):**
1. Verifies you're authenticated to the beta account
2. Deploys `EcrStack` (ECR repository for the Docker image)
3. Deploys `AgentCoreStack` (IAM roles + SSM params for AgentCore)
4. Deploys `KnowledgeBaseStack` (Bedrock Knowledge Base + S3 bucket)
5. Builds Docker image and pushes to ECR
6. Deploys `AppStack` (ECS Fargate + ALB + Cognito)
7. Bootstraps Cognito (creates the `admin` user)
8. Deploys AgentCore runtime, gateway, and memory
9. Also deploys `CrossAccountRoleStack` (IAM role that trusts the orchestrator account)

**Duration:** ~15–20 minutes on first run.

At the end you'll see:
```
[SUCCESS] Application: http://beta-a-Alb16-xxxx.us-east-2.elb.amazonaws.com
```

Save this URL — it's your beta app endpoint.

---

## Step 6: Deploy All Stacks to Prod

```bash
AWS_PROFILE=prod CI=true ./scripts/deploy-all.sh --env prod
```

> `CI=true` skips the interactive production confirmation prompt.

**Duration:** ~15–20 minutes.

At the end you'll see the prod ALB URL. Save it.

---

## Step 7: Seed Pipeline Secrets

The CodePipeline fetches secrets from Secrets Manager in **each target account** at deploy time.
You must seed these before the pipeline runs.

```bash
# Seed secrets into beta account
AWS_PROFILE=beta poetry run python scripts/seed_pipeline_secrets.py --env beta

# Seed secrets into prod account
AWS_PROFILE=prod poetry run python scripts/seed_pipeline_secrets.py --env prod

# Seed secrets into orchestrator account (used by the beta deploy stage)
poetry run python scripts/seed_pipeline_secrets.py --env orchestrator
```

Each command creates a `{stackPrefix}/pipeline-secrets` secret in that account's
Secrets Manager containing `cognito_password`, `langfuse_public_key`, and `langfuse_secret_key`.

> **Why 3 accounts?** The beta CodeBuild stage reads secrets from the orchestrator account
> (via environment variable injection). The prod CodeBuild stage assumes the prod cross-account
> role first, then reads secrets from the prod account directly.

---

## Step 8: Seed Eval Dataset

The pipeline runs LLM-as-judge evaluation tests against beta after each deploy.
Seed the test dataset into Langfuse:

```bash
poetry run python scripts/seed_eval_ci_dataset.py
```

This creates a dataset named `italian-legal-eval-ci` in your Langfuse project with 2 test cases.

> Make sure `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` are set in your
> environment, or add them to a `.env` file:
> ```bash
> export LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx
> export LANGFUSE_SECRET_KEY=sk-lf-xxxxx
> export LANGFUSE_HOST=https://us.cloud.langfuse.com
> ```

---

## Step 9: Deploy the Pipeline Stack to Orchestrator

```bash
cd infra
cdk deploy orchestrator-awslegalpoc-PipelineStack --context env=orchestrator --require-approval never
cd ..
```

This creates:
- **CodePipeline** with 5 stages (Source → DeployBeta → EvalTests → Approval → DeployProd)
- **CodeBuild projects** for beta and prod deployments
- **CodeStar GitHub connection** (needs manual approval — see Step 10)
- **SNS topic** for approval notifications

**Duration:** ~3 minutes.

---

## Step 10: Approve the GitHub Connection

After deploying the pipeline stack, the GitHub connection is in `PENDING` status.
You must manually approve it:

1. Go to **AWS Console (orchestrator account) → Developer Tools → Settings → Connections**
2. Find the connection named `orchestrator-awslegalpoc-github`
3. Click **Update pending connection**
4. Follow the prompts to authorize with GitHub
5. Wait until the status shows **Available**

> Do **not** trigger the pipeline until the connection shows **Available**.
> If the pipeline triggers automatically before you approve, the Source stage will fail.
> You can retry it: **Pipeline → Release change** or retry the Source stage.

---

## Step 11: Verify the Pipeline

Push any change to `main` (or click **Release change** in the console) to trigger the pipeline.

| Stage | What happens | Duration |
|---|---|---|
| **Source** | Pulls code from GitHub | ~30s |
| **DeployBeta** | `deploy-all.sh --env beta --skip-bootstrap --skip-tests` | ~10 min |
| **EvalTests** | LLM-as-judge eval (2 test cases) against beta | ~3 min |
| **Approval** | Manual approval gate (you get an SNS notification) | Manual |
| **DeployProd** | Assumes prod role, `deploy-all.sh --env prod --skip-bootstrap --skip-tests` | ~12 min |

To approve: go to **CodePipeline → orchestrator-awslegalpoc-pipeline → Approve**.

---

## Step 12: Access the Applications

After the pipeline completes (or after your manual deploy in Steps 5–6):

| Environment | URL | Login |
|---|---|---|
| Beta | The ALB URL printed at end of Step 5 | Username: `admin`, Password: from `secrets.json` beta |
| Prod | The ALB URL printed at end of Step 6 | Username: `admin`, Password: from `secrets.json` prod |

---

## Useful Commands

```bash
# Deploy specific environment manually
AWS_PROFILE=beta ./scripts/deploy-all.sh --env beta
AWS_PROFILE=prod CI=true ./scripts/deploy-all.sh --env prod

# Skip specific steps (e.g. after first deploy)
AWS_PROFILE=beta ./scripts/deploy-all.sh --env beta --skip-bootstrap --skip-docker

# Dry run (preview without deploying)
AWS_PROFILE=beta ./scripts/deploy-all.sh --env beta --dry-run

# Test the AgentCore runtime
poetry run python scripts/test_agentcore_runtime.py

# Run eval tests locally
poetry run python scripts/run_eval.py

# Re-seed pipeline secrets (e.g. after rotating Langfuse keys)
AWS_PROFILE=beta poetry run python scripts/seed_pipeline_secrets.py --env beta
AWS_PROFILE=prod poetry run python scripts/seed_pipeline_secrets.py --env prod

# View app logs (ECS)
aws logs tail /ecs/beta-awslegalpoc-app --follow --profile beta
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker not running or user not in docker group | `sudo systemctl start docker` then log out and back in |
| `poetry: command not found` | Poetry not on PATH | `export PATH="$HOME/.local/bin:$PATH"` |
| `AWS credentials are for account X, but target is Y` | Wrong AWS profile | Prefix command with `AWS_PROFILE=beta` or `AWS_PROFILE=prod` |
| `CannotPullContainerError: image not found` | Docker image was never pushed | Re-run deploy-all.sh without `--skip-docker` |
| `AccessDenied s3:ListBucket on ...kb-data` | IAM policy out of sync with bucket name | Re-deploy AppStack (bug was fixed — ensure latest code is deployed) |
| `awslegalpoc/pipeline-secrets` not found in prod | Pipeline secrets not seeded | Run `seed_pipeline_secrets.py --env prod` with prod credentials |
| Pipeline Source stage: `Connection not available` | GitHub connection not yet approved | Approve in Console (Step 10), then retry the Source stage |
| Pipeline runs with old account IDs | Code changes not committed to GitHub | Push `config/environments.json` and other modified files to `main` |
| `Exit status 254` in pre_build | Secret doesn't exist in target account | Seed secrets in that account (Step 7) |
| Prod deploy hangs on confirmation prompt | No TTY in CI environment | Set `CI=true` before running deploy-all.sh |
| `cdk bootstrap` fails with AZ lookup error | Stale AZ cache in cdk.context.json | Delete `cdk.context.json` and retry |
| AgentCore runtime not found | ARN not yet created | Leave `AGENTCORE_RUNTIME_ARN` blank in `.env` — it's stored in SSM after first deploy |
| Bedrock model access denied | Model not enabled in that account | Enable in Bedrock Console → Model access (Step 3) |

---

## Notes on `AGENTCORE_RUNTIME_ARN`

Leave `AGENTCORE_RUNTIME_ARN` **blank** in your `.env` file for fresh account deployments.

The deployment flow is:
1. `agentcore_deploy.py` **creates** the runtime and writes its ARN to SSM at
   `/app/{stackPrefix}/agentcore/runtime_arn`
2. All downstream code checks the env var first, then **falls back to SSM automatically**

You never need to set this manually. After `deploy-all.sh` completes, the ARN is in SSM.

---

## Repository Structure

```
awslegalpoc/
├── config/
│   ├── environments.json          # Account IDs, stack prefixes, model config — committed
│   ├── secrets.example.json       # Template for secrets — committed
│   └── secrets.json               # Actual secrets — GITIGNORED (create from example)
├── infra/                         # CDK infrastructure stacks
│   ├── app.py                     # CDK app entry point
│   ├── ecr_stack.py               # ECR repository
│   ├── app_stack.py               # ECS Fargate + ALB + Cognito
│   ├── agentcore_stack.py         # AgentCore IAM + SSM
│   ├── knowledge_base_stack.py    # Bedrock KB + S3 Vectors
│   ├── pipeline_stack.py          # CodePipeline (orchestrator account only)
│   └── cross_account_role_stack.py # IAM cross-account deploy role (beta + prod)
├── core/                          # Application logic
│   ├── agent.py                   # Strands agent definition
│   ├── tools.py                   # search_knowledge_base tool
│   └── agentcore_runtime_client.py
├── agentcore/
│   └── runtime_app.py             # AgentCore runtime entry point
├── scripts/
│   ├── deploy-all.sh              # Main deployment orchestrator
│   ├── agentcore_deploy.py        # AgentCore runtime + gateway + memory
│   ├── seed_pipeline_secrets.py   # Seed Secrets Manager for pipeline
│   ├── seed_eval_ci_dataset.py    # Seed Langfuse eval dataset
│   ├── bootstrap_cognito.py       # Create Cognito user pool + admin user
│   ├── build.sh / push.sh         # Docker build and ECR push
│   └── run_eval.py                # LLM-as-judge evaluation runner
├── .env.example                   # Template for local dev — committed
└── .env                           # Local dev vars — GITIGNORED
```

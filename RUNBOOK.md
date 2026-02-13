# AWS Legal POC - Deployment Runbook

Quick reference guide for deploying to Beta and Production environments.

## 📋 Prerequisites

- [ ] AWS CLI configured and authenticated
- [ ] Python 3.11+ installed
- [ ] Poetry installed (`pip install poetry`)
- [ ] Docker installed and running
- [ ] Node.js 18+ installed
- [ ] AWS CDK installed (`npm install -g aws-cdk`)

## 🚀 Quick Start

### Deploy to Beta (958502869858)

```bash
cd /path/to/awslegalpoc
./scripts/deploy-all.sh --env beta
```

### Deploy to Prod (072288672152)

```bash
cd /path/to/awslegalpoc
./scripts/deploy-all.sh --env prod
```

## 📁 Configuration Files

### Environment Configuration
**File**: `config/environments.json`
- Contains account IDs, regions, stack prefixes
- Version controlled (committed to git)

### Secrets Configuration
**File**: `config/secrets.json`
- Contains passwords and API keys
- **NOT** version controlled (gitignored)
- Copy from `config/secrets.example.json` and fill in values

## 🔧 Common Operations

### First-Time Setup (Per Account)

```bash
# 1. Configure AWS credentials for target account
aws configure
# or
export AWS_PROFILE=beta-profile

# 2. Bootstrap CDK (one time per account/region)
./scripts/deploy-all.sh --env beta --skip-cdk --skip-docker --skip-agentcore

# 3. Full deployment
./scripts/deploy-all.sh --env beta
```

### Update Only Infrastructure (CDK)

```bash
./scripts/deploy-all.sh --env beta --skip-docker --skip-agentcore --skip-bootstrap
```

### Update Only Application (Docker)

```bash
./scripts/deploy-all.sh --env beta --skip-cdk --skip-agentcore --skip-bootstrap
```

### Update Only AgentCore Runtime

```bash
./scripts/deploy-all.sh --env beta --skip-cdk --skip-docker --skip-bootstrap
```

### Dry Run (See What Would Be Deployed)

```bash
./scripts/deploy-all.sh --env beta --dry-run
```

## 🏗️ Deployment Stages

The unified deployment script runs these stages in order:

1. **Verify AWS Credentials** - Ensures correct account
2. **Bootstrap CDK** (optional) - One-time setup per account
3. **Deploy CDK Stacks**
   - ECR Repository
   - AgentCore Backend (Lambda, DynamoDB)
   - Application Stack (ECS, ALB, Cognito)
4. **Build Docker Image** - Streamlit application
5. **Push to ECR** - Upload image to registry
6. **Bootstrap Cognito** - Create user pool and default user
7. **Deploy AgentCore Runtime** - Deploy agent with Langfuse
8. **Run Tests** (optional) - Post-deployment smoke tests

## 🔐 Managing Secrets

### Update Langfuse Credentials

1. Edit `config/secrets.json`:
```json
{
  "beta": {
    "langfuse": {
      "publicKey": "pk-lf-xxxxx",
      "secretKey": "sk-lf-xxxxx"
    }
  }
}
```

2. Redeploy AgentCore:
```bash
./scripts/deploy-all.sh --env beta --skip-cdk --skip-docker --skip-bootstrap
```

### Update Cognito Password

1. Edit `config/secrets.json`:
```json
{
  "beta": {
    "cognito": {
      "password": "NewSecurePassword123!"
    }
  }
}
```

2. Delete existing user in AWS Console
3. Re-run deployment (or just Cognito bootstrap step)

## 🐛 Troubleshooting

### Issue: "CDK_DEFAULT_ACCOUNT must be set"

**Solution**: Set environment variables before running:
```bash
export AWS_REGION=us-east-2
export CDK_DEFAULT_ACCOUNT=958502869858
export CDK_DEFAULT_REGION=us-east-2
./scripts/deploy-all.sh --env beta
```

### Issue: "ECR repository not found"

**Solution**: Deploy ECR stack first:
```bash
cd infra
cdk deploy beta-awslegalpoc-EcrStack --context env=beta
```

### Issue: "Docker daemon not running"

**Solution**: Start Docker:
```bash
sudo systemctl start docker
# or
sudo service docker start
```

### Issue: "AgentCore deployment fails with 424 error"

**Solution**: Ensure inference profile is configured correctly in `config/environments.json`:
```json
{
  "beta": {
    "bedrockInferenceProfile": "us.amazon.nova-2-lite-v1:0"
  }
}
```

### Issue: "Wrong AWS account"

**Solution**: Switch to correct account/profile:
```bash
# Using profiles
export AWS_PROFILE=beta-profile

# Using aws login
aws login

# Verify
aws sts get-caller-identity
```

## 📊 Post-Deployment Verification

### 1. Check Stack Outputs

```bash
aws cloudformation describe-stacks \
  --stack-name beta-awslegalpoc-AppStack \
  --region us-east-2 \
  --query "Stacks[0].Outputs"
```

### 2. Access Application

- Get ALB URL from stack outputs
- Open in browser: `http://[ALB-URL]`
- Login: username `admin`, password from `config/secrets.json`

### 3. Verify AgentCore

```bash
AWS_REGION=us-east-2 python3.11 -m poetry run python scripts/test_agentcore_runtime.py \
  --prompt "Hello, what tools do you have?"
```

### 4. Check Langfuse

- Go to https://us.cloud.langfuse.com
- Should see traces appearing within 1-2 minutes

### 5. Check CloudWatch Logs

```bash
# ECS application logs
aws logs tail /ecs/beta-awslegalpoc --follow --region us-east-2

# AgentCore runtime logs
aws logs tail /aws/bedrock-agentcore/runtimes/[RUNTIME-ID]-DEFAULT \
  --follow --region us-east-2
```

## 🔄 Rollback Procedures

### Rollback CDK Stack

```bash
# List recent changes
aws cloudformation describe-stack-events \
  --stack-name beta-awslegalpoc-AppStack \
  --region us-east-2 \
  --max-items 20

# Rollback is automatic via CloudFormation on failure
# Manual rollback: update and redeploy with previous version
```

### Rollback ECS Application

```bash
# List task definitions
aws ecs list-task-definitions \
  --family-prefix beta-awslegalpoc \
  --region us-east-2

# Update service to previous task definition
aws ecs update-service \
  --cluster beta-awslegalpoc-Cluster \
  --service beta-awslegalpoc-Service \
  --task-definition beta-awslegalpoc-TaskDef:PREVIOUS_VERSION \
  --region us-east-2
```

### Rollback AgentCore Runtime

AgentCore runtimes are immutable. To "rollback":
1. Redeploy from previous git commit
2. Or keep old runtime ARN and update application to use it

## 🧹 Cleanup / Destroy Environment

### Destroy All Resources

```bash
cd infra

# Destroy stacks in reverse order
cdk destroy beta-awslegalpoc-AppStack --context env=beta
cdk destroy beta-awslegalpoc-AgentCoreStack --context env=beta
cdk destroy beta-awslegalpoc-EcrStack --context env=beta
```

### Manual Cleanup Required

After CDK destroy, manually delete:
- AgentCore Runtime (via AWS Console → Bedrock → AgentCore)
- AgentCore Gateway (via AWS Console → Bedrock → AgentCore)
- AgentCore Memory (via AWS Console → Bedrock → AgentCore)
- CloudWatch Log Groups (optional, for cost savings)

## 📝 Deployment Checklist

### Pre-Deployment
- [ ] Code merged to main branch
- [ ] Tests passing locally
- [ ] AWS credentials configured for target account
- [ ] Secrets configured in `config/secrets.json`
- [ ] Team notified (for prod deployments)

### During Deployment
- [ ] Run deployment script with correct environment
- [ ] Monitor CloudWatch logs for errors
- [ ] Verify each stage completes successfully

### Post-Deployment
- [ ] Access application URL
- [ ] Test basic functionality (login, chat)
- [ ] Verify AgentCore runtime working
- [ ] Check Langfuse traces appearing
- [ ] Update team/stakeholders

## 🆘 Emergency Contacts

- **DevOps Lead**: [Contact Info]
- **AWS Support**: [Account Number / Support Plan]
- **Slack Channel**: #aws-legal-poc

## 📚 Additional Resources

- [CICD_DESIGN.md](CICD_DESIGN.md) - Full CI/CD architecture
- [DEPLOYMENT.md](DEPLOYMENT.md) - Detailed deployment guide
- [README.md](README.md) - Project overview
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
- [Bedrock AgentCore Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)

## 🔖 Quick Command Reference

```bash
# Deploy to beta
./scripts/deploy-all.sh --env beta

# Deploy to prod
./scripts/deploy-all.sh --env prod

# Update only app code (fast)
./scripts/deploy-all.sh --env beta --skip-cdk --skip-agentcore --skip-bootstrap

# Full help
./scripts/deploy-all.sh --help

# Check AWS account
aws sts get-caller-identity

# View logs
aws logs tail [LOG_GROUP] --follow --region us-east-2

# Verify ECS service
aws ecs describe-services --cluster [CLUSTER] --services [SERVICE] --region us-east-2
```

# AWS Legal POC - Deployment Guide

This guide explains how to deploy the AWS Legal POC application (Bedrock AgentCore + Streamlit) to a new AWS account.

## Prerequisites

### AWS Account Requirements
- AWS Account with appropriate permissions
- Ability to create: IAM roles, ECS clusters, ECR repositories, ALB, Lambda, DynamoDB, Bedrock AgentCore resources
- Bedrock model access enabled (Amazon Nova models)

### Local Development Environment
- AWS CLI configured with credentials
- Python 3.11+
- Node.js 18+ (for CDK CLI)
- Docker (for building container images)
- CDK installed: `npm install -g aws-cdk`

### Optional: Langfuse Account
- Sign up at https://cloud.langfuse.com for observability
- Get your API keys for LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY

## Deployment Steps

### 1. Clone and Configure

```bash
git clone <repository-url>
cd awslegalpoc

# Copy and configure environment file
cp .env.example .env
# Edit .env with your values (region, Langfuse keys, etc.)
```

### 2. Bootstrap CDK (First Time Only)

```bash
export AWS_REGION=us-east-2  # or your preferred region
cd infra
cdk bootstrap
```

### 3. Deploy Infrastructure Stacks

```bash
# Deploy ECR repository
cdk deploy AwsLegalPocEcrStack --require-approval never

# Deploy AgentCore backend resources (Lambda, DynamoDB, Knowledge Base)
cdk deploy AwsLegalPocAgentCoreStack --require-approval never
```

### 4. Build and Push Docker Image

```bash
cd ..
./scripts/build-and-push.sh
```

### 5. Deploy Application Stack (ECS + ALB + Cognito)

```bash
cd infra
cdk deploy AwsLegalPocAppStack --require-approval never
```

This will output your application URL.

### 6. Deploy AgentCore Runtime, Gateway, and Memory

```bash
cd ..
python3 scripts/agentcore_deploy.py --wait
```

This will:
- Create AgentCore Memory with STM + LTM strategies
- Set up AgentCore Gateway with Cognito JWT authentication
- Deploy AgentCore Runtime with your agent code
- Configure Lambda gateway target

### 7. Seed Memory Data (Optional)

```bash
python3 scripts/seed_memory.py
```

This populates the memory with sample customer preferences and history.

### 8. Update Application to Use AgentCore

The .env file will be automatically updated with AGENTCORE_RUNTIME_ARN. To enable AgentCore mode:

```bash
# Update ECS task with AgentCore configuration
python3 scripts/update_ecs_with_agentcore.py  # TODO: Create this helper script
# OR manually update ECS task definition environment variables
```

## Testing the Deployment

1. **Access the Application**
   - Use the ALB URL from step 5 (HTTP, not HTTPS)
   - Default credentials: admin / ChangeMe123!

2. **Test AgentCore Runtime Directly**
   ```bash
   python3 scripts/test_agentcore_runtime.py --prompt "List all of your tools"
   ```

3. **Check Observability**
   - CloudWatch Logs: `/aws/bedrock-agentcore/runtimes/...`
   - Langfuse Dashboard: https://cloud.langfuse.com (if configured)

## Architecture Overview

```
User → ALB → ECS (Streamlit) → AgentCore Runtime
                                      ↓
                           ┌──────────┴──────────┐
                           ↓                     ↓
                    AgentCore Memory    AgentCore Gateway
                    (STM + LTM)              ↓
                                        Lambda Tools
                                        (DynamoDB, Web Search)
```

## Troubleshooting

### CDK Bootstrap Fails
- Ensure AWS credentials have admin-level permissions
- Check if CDKToolkit stack already exists

### Docker Build Fails
- Ensure Docker daemon is running
- Check ECR repository exists and you have push permissions

### AgentCore Deployment Fails
- Verify Bedrock model access is enabled
- Check CloudWatch logs for detailed errors
- Ensure IAM roles have correct permissions

### Gateway 401 Errors
- Verify Cognito user pool exists
- Check gateway authorizer configuration matches Cognito pool
- Ensure JWT token is valid

### Model Invocation Errors
- Verify you're using inference profile ARN, not model ID
- Check region supports the selected model
- Ensure BEDROCK_INFERENCE_PROFILE_ARN is set

## Cost Considerations

- **ECS Fargate**: ~$30-50/month (1 task, minimal specs)
- **ALB**: ~$20-25/month
- **Bedrock AgentCore**: Pay per invocation
- **Bedrock Nova Models**: Pay per token
- **DynamoDB**: Pay per request (on-demand)
- **ECR**: Storage costs (minimal)

## Clean Up

To remove all resources:

```bash
cd infra
cdk destroy AwsLegalPocAppStack
cdk destroy AwsLegalPocAgentCoreStack  
cdk destroy AwsLegalPocEcrStack

# Manually delete:
# - AgentCore Runtime via AWS Console
# - AgentCore Gateway via AWS Console
# - AgentCore Memory via AWS Console
```

## Support

For issues or questions:
- Check CloudWatch logs for error details
- Review AWS Bedrock AgentCore documentation
- Check CDK documentation for infrastructure issues

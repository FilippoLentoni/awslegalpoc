# CI/CD Design for AWS Legal POC

## Overview
Multi-account deployment pipeline with AWS CodePipeline deploying to Beta (958502869858) and Prod (072288672152).

## Architecture

### Current State Issues
1. **Multiple manual scripts** - Requires 8+ steps to deploy
2. **No automation** - Manual deployment to each environment
3. **No promotion process** - No way to safely promote from beta to prod
4. **Configuration scattered** - .env files, CDK context, scripts

### Proposed Solution

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CodeCommit / GitHub                         │
│                      (Source Code Repository)                       │
└────────────────────┬────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       CodePipeline (Tools Account)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   Source     │→ │    Build     │→ │   Deploy Beta            │  │
│  │              │  │ (CodeBuild)  │  │   (958502869858)         │  │
│  └──────────────┘  └──────────────┘  └──────────┬───────────────┘  │
│                                                  │                   │
│                                                  ▼                   │
│                                      ┌────────────────────────────┐ │
│                                      │  Manual Approval           │ │
│                                      └────────────┬───────────────┘ │
│                                                   │                  │
│                                                   ▼                  │
│                                      ┌────────────────────────────┐ │
│                                      │   Deploy Prod              │ │
│                                      │   (072288672152)           │ │
│                                      └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## Best Practices Implementation

### 1. Environment Configuration
Use CDK context and SSM Parameter Store instead of .env files:

```typescript
// cdk.context.json
{
  "environments": {
    "beta": {
      "account": "958502869858",
      "region": "us-east-2",
      "stackPrefix": "beta-awslegalpoc"
    },
    "prod": {
      "account": "072288672152",
      "region": "us-east-2",
      "stackPrefix": "awslegalpoc"
    }
  }
}
```

### 2. Unified Deployment Script
Single `deploy.py` script that:
- Accepts environment parameter (--env beta|prod)
- Reads configuration from context
- Executes all deployment steps in order
- Handles errors and rollbacks

### 3. CodePipeline Stages

#### Stage 1: Source
- Trigger on git push to main branch
- Pull source code from repository

#### Stage 2: Build
- Run tests
- Build Docker image
- Push to ECR (in target account)
- Synthesize CDK templates

#### Stage 3: Deploy to Beta (958502869858)
- Deploy ECR stack
- Deploy AgentCore backend
- Deploy application stack
- Deploy AgentCore runtime
- Run smoke tests

#### Stage 4: Manual Approval
- Slack/Email notification
- Manual approval gate
- QA verification in beta

#### Stage 5: Deploy to Prod (072288672152)
- Same steps as beta
- Deploy with prod configuration
- Run smoke tests
- Notify on completion

## Cross-Account Access

### IAM Roles Required

1. **In Tools Account** (where CodePipeline runs):
   ```
   CodePipelineServiceRole
   CodeBuildServiceRole
   ```

2. **In Beta Account (958502869858)**:
   ```
   CrossAccountDeploymentRole
   - Trust: Tools account CodeBuild
   - Permissions: CDK deployment, ECS, ECR, etc.
   ```

3. **In Prod Account (072288672152)**:
   ```
   CrossAccountDeploymentRole
   - Same as beta
   ```

## Deployment Script Structure

```
scripts/
├── deploy.py              # Main deployment orchestrator
├── build_and_push.py      # Docker build/push
├── deploy_cdk_stacks.py   # CDK deployment
├── deploy_agentcore.py    # AgentCore deployment
├── smoke_tests.py         # Post-deployment tests
└── rollback.py            # Rollback handler
```

## Environment-Specific Resources

### Naming Convention
```
{env}-awslegalpoc-{resource}
```

Examples:
- Beta ECR: `beta-awslegalpoc-streamlit`
- Beta ECS Service: `beta-awslegalpoc-service`
- Prod ECR: `awslegalpoc-streamlit`
- Prod ECS Service: `awslegalpoc-service`

### Resource Isolation
- Separate VPCs per environment
- Separate Cognito user pools
- Separate DynamoDB tables
- Separate AgentCore runtimes

## Configuration Management

### Option 1: SSM Parameter Store (Recommended)
```
/awslegalpoc/beta/langfuse/public-key
/awslegalpoc/beta/langfuse/secret-key
/awslegalpoc/prod/langfuse/public-key
/awslegalpoc/prod/langfuse/secret-key
```

### Option 2: Secrets Manager
```
beta/awslegalpoc/langfuse
prod/awslegalpoc/langfuse
```

## Rollback Strategy

1. **CDK Stack Rollback**: Automatic via CloudFormation
2. **AgentCore Rollback**: Keep previous version, switch alias
3. **ECS Rollback**: Update service to previous task definition
4. **Database Rollback**: Automated snapshots + restore

## Testing Strategy

### Pre-deployment Tests (CodeBuild)
- Unit tests
- Integration tests
- CDK synth validation

### Post-deployment Tests (Smoke Tests)
- Health check endpoint
- Sample AgentCore invocation
- Database connectivity
- Langfuse integration

## Security Considerations

1. **Secrets Management**
   - No secrets in git
   - Use AWS Secrets Manager
   - Rotate credentials regularly

2. **Least Privilege**
   - Minimal IAM permissions
   - Time-bound assume role
   - Audit logs enabled

3. **Network Security**
   - VPC isolation
   - Security groups
   - Private subnets for compute

## Monitoring & Observability

1. **Pipeline Monitoring**
   - CloudWatch Logs for CodePipeline
   - SNS notifications on failure
   - Slack/Email alerts

2. **Application Monitoring**
   - Langfuse traces
   - CloudWatch metrics
   - Application Performance Monitoring (APM)

## Cost Optimization

1. **Resource Tagging**
   ```
   Environment: beta|prod
   Project: awslegalpoc
   ManagedBy: codepipeline
   ```

2. **Auto-scaling**
   - Scale down beta during off-hours
   - Production always available

3. **Resource Cleanup**
   - Automated cleanup of old ECR images
   - Retention policies on logs

## Implementation Timeline

### Phase 1: Restructure Code (Week 1)
- Create unified deployment script
- Externalize configuration
- Update CDK stacks with environment awareness

### Phase 2: Setup Cross-Account Access (Week 1)
- Create IAM roles in beta/prod
- Configure trust relationships
- Test cross-account access

### Phase 3: Build CodePipeline (Week 2)
- Create pipeline definition
- Configure buildspec.yml
- Setup manual approval

### Phase 4: Testing & Validation (Week 2)
- Deploy to beta via pipeline
- Run smoke tests
- Promote to prod

### Phase 5: Documentation & Training (Week 3)
- Update runbooks
- Document rollback procedures
- Train team on pipeline usage

## Next Steps

1. Review and approve this design
2. Decide on tools account (or use beta as tools account)
3. Create deployment orchestration script
4. Setup IAM roles for cross-account access
5. Implement CodePipeline

---

## Implementation Status - Option A (Quick Win) ✅

### Completed

1. **Environment Configuration**
   - ✅ Created `config/environments.json` for beta and prod
   - ✅ Created `config/secrets.json` for sensitive data (gitignored)
   - ✅ Created `config/secrets.example.json` as template

2. **CDK Infrastructure Updates**
   - ✅ Updated `infra/app.py` to load environment config
   - ✅ Modified `AwsLegalPocEcrStack` to accept env parameters
   - ✅ Modified `AwsLegalPocAgentCoreStack` to accept env parameters
   - ✅ Modified `AwsLegalPocAppStack` to accept env parameters
   - ✅ Added resource tagging support to all stacks

3. **Unified Deployment Script**
   - ✅ Created `scripts/deploy-all.sh` with full orchestration
   - ✅ Supports `--env beta|prod` parameter
   - ✅ Includes safety checks and confirmations for prod
   - ✅ Provides skip flags (--skip-bootstrap, --skip-cdk, etc.)
   - ✅ Color-coded output for better UX

4. **Helper Scripts Updated**
   - ✅ Updated `scripts/push.sh` to support env-specific ECR repos

### File Structure
```
awslegalpoc/
├── config/
│   ├── environments.json      # Environment configuration
│   ├── secrets.json           # Secrets (gitignored)
│   └── secrets.example.json   # Template for secrets
├── infra/
│   ├── app.py                 # ✅ Updated with env awareness
│   ├── ecr_stack.py          # ✅ Updated with env parameters
│   ├── agentcore_stack.py    # ✅ Updated with env parameters
│   └── app_stack.py          # ✅ Updated with env parameters
└── scripts/
    ├── deploy-all.sh          # ✅ NEW: Unified deployment
    ├── push.sh                # ✅ Updated for env-specific repos
    ├── build.sh               # Existing
    ├── bootstrap_cognito.py   # Existing
    └── agentcore_deploy.py    # Existing
```

### Usage Examples

**Deploy to Beta (Full)**
```bash
./scripts/deploy-all.sh --env beta
```

**Deploy to Prod (with confirmation)**
```bash
./scripts/deploy-all.sh --env prod
```

**Partial Deployment (Skip Docker)**
```bash
./scripts/deploy-all.sh --env beta --skip-docker --skip-agentcore
```

**Dry Run**
```bash
./scripts/deploy-all.sh --env beta --dry-run
```

### Benefits Achieved

1. ✅ **Single Command Deployment** - No more running 8+ manual steps
2. ✅ **Environment Isolation** - Separate configs for beta/prod
3. ✅ **Safety Checks** - Confirmation prompt for prod deployments
4. ✅ **Flexibility** - Skip flags for selective deployment
5. ✅ **Consistency** - Same process for all environments
6. ✅ **Resource Tagging** - Automatic tagging for cost tracking
7. ✅ **No Hardcoded Values** - All config externalized

### Updated Implementation Timeline

- ✅ Phase 1: Restructure Code (COMPLETED)
  - ✅ Create unified deployment script
  - ✅ Externalize configuration
  - ✅ Update CDK stacks with environment awareness
  - ✅ Add tagging support

- ⏳ Phase 2: Setup Cross-Account Access (NEXT)
  - Create IAM roles in prod account
  - Configure trust relationships from beta → prod
  - Test cross-account deployment

- ⏳ Phase 3: Build CodePipeline (FUTURE)
  - Create pipeline definition
  - Configure buildspec.yml
  - Setup manual approval


#!/usr/bin/env bash
#
# Unified Deployment Script for AWS Legal POC
# Deploys all infrastructure and application components to a target environment
#
# Usage:
#   ./scripts/deploy-all.sh --env beta
#   ./scripts/deploy-all.sh --env prod --skip-bootstrap
#   ./scripts/deploy-all.sh --env beta --skip-agentcore
#

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENV=""
SKIP_BOOTSTRAP=false
SKIP_CDK=false
SKIP_DOCKER=false
SKIP_AGENTCORE=false
SKIP_TESTS=false
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        --skip-bootstrap)
            SKIP_BOOTSTRAP=true
            shift
            ;;
        --skip-cdk)
            SKIP_CDK=true
            shift
            ;;
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
        --skip-agentcore)
            SKIP_AGENTCORE=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            cat << EOF
Usage: $0 --env <beta|prod> [OPTIONS]

Options:
    --env <environment>     Target environment (required): beta or prod
    --skip-bootstrap       Skip CDK bootstrap step
    --skip-cdk            Skip CDK stack deployment
    --skip-docker         Skip Docker build and push
    --skip-agentcore      Skip AgentCore runtime deployment
    --skip-tests          Skip post-deployment tests
    --dry-run             Show what would be deployed without deploying
    -h, --help            Show this help message

Examples:
    # Full deployment to beta
    $0 --env beta

    # Deploy to prod, skip bootstrap (already done)
    $0 --env prod --skip-bootstrap

    # Only deploy CDK stacks, skip Docker and AgentCore
    $0 --env beta --skip-docker --skip-agentcore

    # Dry run to see what would happen
    $0 --env beta --dry-run
EOF
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Validate environment
if [[ -z "${ENV}" ]]; then
    echo -e "${RED}Error: --env is required${NC}"
    echo "Use --help for usage information"
    exit 1
fi

if [[ "${ENV}" != "beta" && "${ENV}" != "prod" ]]; then
    echo -e "${RED}Error: --env must be 'beta' or 'prod'${NC}"
    exit 1
fi

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}========================================${NC}"
}

# Load configuration
CONFIG_FILE="${PROJECT_ROOT}/config/environments.json"
SECRETS_FILE="${PROJECT_ROOT}/config/secrets.json"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    log_error "Configuration file not found: ${CONFIG_FILE}"
    exit 1
fi

# Extract configuration using Python (more reliable than jq)
ACCOUNT=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['account'])")
REGION=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['region'])")
STACK_PREFIX=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['stackPrefix'])")
ECR_REPO=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['ecrRepository'])")

log_info "Deployment Configuration:"
log_info "  Environment: ${ENV}"
log_info "  Account:     ${ACCOUNT}"
log_info "  Region:      ${REGION}"
log_info "  Prefix:      ${STACK_PREFIX}"

if [[ "${DRY_RUN}" == "true" ]]; then
    log_warn "DRY RUN MODE - No actual deployment will occur"
    exit 0
fi

# Confirm deployment
if [[ "${ENV}" == "prod" ]]; then
    echo ""
    log_warn "You are about to deploy to PRODUCTION (${ACCOUNT})"
    read -p "Are you sure you want to continue? (yes/no): " CONFIRM
    if [[ "${CONFIRM}" != "yes" ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi
fi

# Export environment variables for CDK and scripts
export AWS_REGION="${REGION}"
export AWS_DEFAULT_REGION="${REGION}"
export CDK_DEFAULT_ACCOUNT="${ACCOUNT}"
export CDK_DEFAULT_REGION="${REGION}"
export DEPLOY_ENV="${ENV}"

# Verify AWS credentials
log_step "Step 0: Verifying AWS Credentials"
CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
if [[ -z "${CURRENT_ACCOUNT}" ]]; then
    log_error "Failed to get AWS credentials. Run 'aws login' or configure credentials"
    exit 1
fi

if [[ "${CURRENT_ACCOUNT}" != "${ACCOUNT}" ]]; then
    log_error "AWS credentials are for account ${CURRENT_ACCOUNT}, but target is ${ACCOUNT}"
    log_error "Please switch to the correct AWS account/profile"
    exit 1
fi

log_success "Authenticated to AWS account ${CURRENT_ACCOUNT}"

# Step 1: Bootstrap CDK
if [[ "${SKIP_BOOTSTRAP}" == "false" ]]; then
    log_step "Step 1: Bootstrapping CDK"
    cd "${PROJECT_ROOT}/infra"

    # Check if already bootstrapped
    if aws cloudformation describe-stacks --stack-name CDKToolkit --region "${REGION}" &>/dev/null; then
        log_info "CDK already bootstrapped in this account/region"
    else
        log_info "Bootstrapping CDK..."
        cdk bootstrap aws://${ACCOUNT}/${REGION}
        log_success "CDK bootstrapped"
    fi
else
    log_info "Skipping CDK bootstrap (--skip-bootstrap)"
fi

# Step 2: Deploy CDK Stacks
if [[ "${SKIP_CDK}" == "false" ]]; then
    log_step "Step 2: Deploying CDK Infrastructure"
    cd "${PROJECT_ROOT}/infra"

    log_info "Installing CDK dependencies..."
    if [[ ! -d ".venv" ]]; then
        python3 -m venv .venv
    fi
    .venv/bin/pip install -q -r requirements.txt

    log_info "Deploying ECR Stack..."
    cdk deploy "${STACK_PREFIX}-EcrStack" \
        --context env="${ENV}" \
        --require-approval never
    log_success "ECR Stack deployed"

    log_info "Deploying AgentCore Backend Stack..."
    cdk deploy "${STACK_PREFIX}-AgentCoreStack" \
        --context env="${ENV}" \
        --require-approval never
    log_success "AgentCore Backend Stack deployed"

    log_info "Deploying Knowledge Base Stack..."
    cdk deploy "${STACK_PREFIX}-KnowledgeBaseStack" \
        --context env="${ENV}" \
        --require-approval never
    log_success "Knowledge Base Stack deployed"

    cd "${PROJECT_ROOT}"
else
    log_info "Skipping CDK deployment (--skip-cdk)"
fi

# Step 3: Build and Push Docker Image
if [[ "${SKIP_DOCKER}" == "false" ]]; then
    log_step "Step 3: Building and Pushing Docker Image"

    export AWS_REGION="${REGION}"
    export REPO_NAME="${ECR_REPO}"

    log_info "Building Docker image..."
    "${PROJECT_ROOT}/scripts/build.sh"
    log_success "Docker image built"

    log_info "Pushing to ECR (${ECR_REPO})..."
    "${PROJECT_ROOT}/scripts/push.sh"
    log_success "Docker image pushed to ECR"
else
    log_info "Skipping Docker build/push (--skip-docker)"
fi

# Step 4: Deploy Application Stack (ECS + ALB)
if [[ "${SKIP_CDK}" == "false" ]]; then
    log_step "Step 4: Deploying Application Stack"
    cd "${PROJECT_ROOT}/infra"

    log_info "Deploying App Stack (ECS + ALB + Cognito)..."
    cdk deploy "${STACK_PREFIX}-AppStack" \
        --context env="${ENV}" \
        --require-approval never
    log_success "Application Stack deployed"

    # Get ALB URL
    ALB_URL=$(aws cloudformation describe-stacks \
        --stack-name "${STACK_PREFIX}-AppStack" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='AlbUrl'].OutputValue" \
        --output text)

    log_success "Application URL: ${ALB_URL}"

    cd "${PROJECT_ROOT}"
fi

# Step 5: Bootstrap Cognito
log_step "Step 5: Bootstrapping Cognito"
if [[ -f "${SECRETS_FILE}" ]]; then
    log_info "Setting up Cognito user pool and user..."
    export COGNITO_USERNAME=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['cognitoUsername'])")
    export COGNITO_PASSWORD=$(python3 -c "import json; print(json.load(open('${SECRETS_FILE}'))['${ENV}']['cognito']['password'])")
    export COGNITO_POOL_NAME="${STACK_PREFIX}-temp-pool"
    export COGNITO_CLIENT_NAME="${STACK_PREFIX}-temp-client"
    export COGNITO_CONFIG_SECRET="${STACK_PREFIX}/cognito-config"

    cd "${PROJECT_ROOT}"
    python3.11 -m poetry run python "${PROJECT_ROOT}/scripts/bootstrap_cognito.py"
    log_success "Cognito configured"
else
    log_warn "Secrets file not found, skipping Cognito bootstrap"
fi

# Step 6: Deploy AgentCore Runtime
if [[ "${SKIP_AGENTCORE}" == "false" ]]; then
    log_step "Step 6: Deploying AgentCore Runtime"

    # Export Langfuse credentials if available
    if [[ -f "${SECRETS_FILE}" ]]; then
        export LANGFUSE_PUBLIC_KEY=$(python3 -c "import json; print(json.load(open('${SECRETS_FILE}'))['${ENV}']['langfuse']['publicKey'])" 2>/dev/null || echo "")
        export LANGFUSE_SECRET_KEY=$(python3 -c "import json; print(json.load(open('${SECRETS_FILE}'))['${ENV}']['langfuse']['secretKey'])" 2>/dev/null || echo "")
        export LANGFUSE_HOST=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['langfuseHost'])")
    fi

    export COGNITO_CONFIG_SECRET="${STACK_PREFIX}/cognito-config"
    export APP_VERSION="${ENV}"

    # Read model config from environments.json
    export BEDROCK_MODEL_ID=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['bedrockModelId'])" 2>/dev/null || echo "")
    export BEDROCK_INFERENCE_PROFILE_ARN=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['bedrockInferenceProfile'])" 2>/dev/null || echo "")
    if [[ -n "${BEDROCK_INFERENCE_PROFILE_ARN}" ]]; then
        log_info "Model: ${BEDROCK_INFERENCE_PROFILE_ARN}"
    fi

    # Read Knowledge Base ID from SSM (set by KnowledgeBaseStack)
    # Uses /app/ prefix to avoid reserved SSM namespaces
    KNOWLEDGE_BASE_ID=$(aws ssm get-parameter \
        --name "/app/${STACK_PREFIX}/kb/knowledge-base-id" \
        --region "${REGION}" \
        --query "Parameter.Value" \
        --output text 2>/dev/null || echo "")
    if [[ -n "${KNOWLEDGE_BASE_ID}" ]]; then
        export KNOWLEDGE_BASE_ID
        log_info "Knowledge Base ID: ${KNOWLEDGE_BASE_ID}"
    else
        log_warn "Knowledge Base ID not found in SSM — KB search will be disabled"
    fi

    log_info "Deploying AgentCore runtime, gateway, and memory..."
    python3.11 -m poetry run python "${PROJECT_ROOT}/scripts/agentcore_deploy.py" --cognito-secret "${STACK_PREFIX}/cognito-config" --wait
    log_success "AgentCore runtime deployed"
else
    log_info "Skipping AgentCore deployment (--skip-agentcore)"
fi

# Step 7: Run Post-Deployment Tests (LLM-as-judge eval on beta only)
if [[ "${SKIP_TESTS}" == "false" ]]; then
    log_step "Step 7: Running Post-Deployment Tests"

    if [[ "${ENV}" == "beta" ]]; then
        log_info "Running LLM-as-judge evaluation against beta..."

        # Ensure Langfuse credentials are exported
        if [[ -f "${SECRETS_FILE}" ]]; then
            export LANGFUSE_PUBLIC_KEY=$(python3 -c "import json; print(json.load(open('${SECRETS_FILE}'))['${ENV}']['langfuse']['publicKey'])" 2>/dev/null || echo "")
            export LANGFUSE_SECRET_KEY=$(python3 -c "import json; print(json.load(open('${SECRETS_FILE}'))['${ENV}']['langfuse']['secretKey'])" 2>/dev/null || echo "")
        fi
        export LANGFUSE_HOST=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}']['langfuseHost'])" 2>/dev/null || echo "https://us.cloud.langfuse.com")
        export COGNITO_CONFIG_SECRET="${STACK_PREFIX}/cognito-config"
        export DEPLOY_ENV="${ENV}"

        # Wait for runtime to stabilize after deployment
        log_info "Waiting 30 seconds for runtime to stabilize..."
        sleep 30

        EVAL_DATASET=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}'].get('eval', {}).get('dataset', 'italian-legal-eval'))")
        EVAL_MIN_SCORE=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}'].get('eval', {}).get('minScore', 0.5))")
        EVAL_TIMEOUT=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}'))['${ENV}'].get('eval', {}).get('timeout', 180))")
        log_info "Eval config: dataset=${EVAL_DATASET}, minScore=${EVAL_MIN_SCORE}, timeout=${EVAL_TIMEOUT}"

        if python3.11 -m poetry run python "${PROJECT_ROOT}/scripts/run_eval.py" \
            --dataset "${EVAL_DATASET}" \
            --min-score "${EVAL_MIN_SCORE}" \
            --timeout "${EVAL_TIMEOUT}"; then
            log_success "Evaluation passed!"
        else
            log_warn "Evaluation FAILED. Check Langfuse for details."
            log_warn "Deployment completed but evaluation did not pass threshold."
            # Note: does not exit 1 — change to 'exit 1' to gate deployments on eval
        fi
    else
        log_info "Skipping evaluation for ${ENV} environment (eval runs on beta only)"
    fi
else
    log_info "Skipping post-deployment tests (--skip-tests)"
fi

# Summary
log_step "Deployment Complete!"
echo ""
log_success "Environment:  ${ENV}"
log_success "Account:      ${ACCOUNT}"
log_success "Region:       ${REGION}"
if [[ -n "${ALB_URL:-}" ]]; then
    log_success "Application:  ${ALB_URL}"
fi
echo ""
log_info "Next steps:"
log_info "  1. Access the application at the URL above"
log_info "  2. Login with username: admin"
log_info "  3. Check Langfuse for traces: https://us.cloud.langfuse.com"
log_info "  4. Monitor CloudWatch logs for any issues"
echo ""
log_info "To deploy to another environment, run:"
log_info "  $0 --env <beta|prod>"
echo ""

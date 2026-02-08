# Langfuse Observability Integration

## Changes Made

### 1. Runtime Application ([agentcore/runtime_app.py](agentcore/runtime_app.py))
Added Strands telemetry initialization to enable OpenTelemetry export to Langfuse:

```python
from strands.telemetry import StrandsTelemetry

# Initialize Strands telemetry for Langfuse observability
strands_telemetry = StrandsTelemetry()
strands_telemetry.setup_otlp_exporter()
```

### 2. Deployment Script ([scripts/agentcore_deploy.py](scripts/agentcore_deploy.py))

**Added disable_otel flag:**
```python
runtime.configure(
    # ... other config ...
    disable_otel=True,  # Disable AgentCore default observability to use Langfuse
)
```

**Added Langfuse OTEL environment variables:**
```python
# Create base64-encoded auth header for Langfuse
langfuse_auth_token = base64.b64encode(
    f"{langfuse_public_key}:{langfuse_secret_key}".encode()
).decode()

env_vars.update({
    "OTEL_EXPORTER_OTLP_ENDPOINT": f"{langfuse_host}/api/public/otel",
    "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization=Basic {langfuse_auth_token}",
    "DISABLE_ADOT_OBSERVABILITY": "true",
})
```

### 3. Requirements
Already included in [agentcore/requirements.txt](agentcore/requirements.txt):
```
strands-agents[otel]>=1.25.0,<2.0.0
```

## How to Deploy with Langfuse

### Option 1: Using .env file (Recommended)
```bash
# Ensure .env has Langfuse credentials
cat .env | grep LANGFUSE

# Deploy with .env loaded
set -a && source .env && set +a
python3 scripts/agentcore_deploy.py --cognito-secret awslegalpoc/cognito-config
```

### Option 2: Using environment variables
```bash
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_HOST="https://us.cloud.langfuse.com"
export BEDROCK_INFERENCE_PROFILE_ARN="arn:aws:bedrock:us-east-2:878817878019:inference-profile/us.amazon.nova-2-lite-v1:0"

python3 scripts/agentcore_deploy.py --cognito-secret awslegalpoc/cognito-config
```

## Verifying Langfuse Integration

### 1. Check Deployment Output
You should see:
```
✅ Langfuse observability configured: https://us.cloud.langfuse.com
```

If you see:
```
⚠️ Langfuse credentials not found - observability will not be enabled
```
Then the LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY environment variables are not set.

### 2. Test Runtime
```bash
python3 scripts/test_agentcore_runtime.py --prompt "What tools do you have?"
```

### 3. Check Langfuse Dashboard
1. Go to https://cloud.langfuse.com
2. Navigate to your project
3. Click on "Traces" in the left sidebar
4. You should see traces with:
   - Agent invocation details
   - Tool calls (web_search, get_product_info, etc.)
   - Model interactions with latency and token usage
   - Request/response payloads

### 4. Check Runtime Logs (Optional)
```bash
aws logs tail /aws/bedrock-agentcore/runtimes/awslegalpoc_customer_support-DA7b363BSQ-DEFAULT \
  --region us-east-2 --since 5m --format short
```

## Architecture

```
User Request
    ↓
AgentCore Runtime
    ↓
Strands Agent (with telemetry)
    ↓
OpenTelemetry Exporter
    ↓
Langfuse API (via OTEL endpoint)
    ↓
Langfuse Dashboard
```

## Key Differences from AgentCore Default Observability

| Feature | AgentCore Default | Langfuse Integration |
|---------|-------------------|---------------------|
| OTEL Export | AWS X-Ray & CloudWatch | Langfuse OTEL endpoint |
| Configuration | `disable_otel=False` | `disable_otel=True` |
| Environment Variables | None | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `DISABLE_ADOT_OBSERVABILITY` |
| Telemetry Initialization | Automatic | Explicit (`StrandsTelemetry().setup_otlp_exporter()`) |
| Dashboard | AWS Console | Langfuse web UI |

## Troubleshooting

### Traces not appearing in Langfuse

1. **Check credentials are valid:**
   ```bash
   echo $LANGFUSE_SECRET_KEY
   echo $LANGFUSE_PUBLIC_KEY
   ```

2. **Verify OTEL endpoint is correct:**
   - Should be: `https://us.cloud.langfuse.com/api/public/otel`
   - For EU: `https://cloud.langfuse.com/api/public/otel`

3. **Check runtime environment variables:**
   ```bash
   aws ecs describe-task-definition \
     --task-definition AwsLegalPocAppStackTaskDef1F8925FC:latest \
     --region us-east-2 | jq '.taskDefinition.containerDefinitions[0].environment'
   ```

4. **Verify telemetry is initialized:**
   - Check runtime logs for StrandsTelemetry initialization messages

### Authentication errors

If you see 401 errors in logs:
- Verify the base64 encoding of `public_key:secret_key` is correct
- Ensure no extra quotes or spaces in the credentials
- Test credentials with a simple curl command:
  ```bash
  echo -n "pk-lf-...:sk-lf-..." | base64
  ```

## References

- [Langfuse OTEL Documentation](https://langfuse.com/docs/integrations/opentelemetry)
- [Strands Agents Telemetry](https://strandsagents.com/latest/user-guide/observability/)
- [AgentCore Runtime Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)

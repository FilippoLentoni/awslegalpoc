import argparse
import base64
import json
import os
import shutil
import time
from pathlib import Path
from typing import Dict

import boto3
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType
from bedrock_agentcore_starter_toolkit import Runtime


def _region() -> str:
    return (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or boto3.session.Session().region_name
        or "us-east-2"
    )


def _ssm_client():
    return boto3.client("ssm", region_name=_region())


def _secrets_client():
    return boto3.client("secretsmanager", region_name=_region())


def put_ssm_parameter(name: str, value: str) -> None:
    _ssm_client().put_parameter(Name=name, Value=value, Type="String", Overwrite=True)


def get_ssm_parameter(name: str) -> str:
    return _ssm_client().get_parameter(Name=name, WithDecryption=False)["Parameter"]["Value"]


def ensure_cognito_params(secret_name: str) -> Dict[str, str]:
    secret = _secrets_client().get_secret_value(SecretId=secret_name)
    config = json.loads(secret["SecretString"])

    pool_id = config["pool_id"]
    client_id = config["client_id"]
    client_secret = config["client_secret"]

    discovery_url = (
        f"https://cognito-idp.{_region()}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
    )

    put_ssm_parameter("/app/customersupport/agentcore/pool_id", pool_id)
    put_ssm_parameter("/app/customersupport/agentcore/client_id", client_id)
    put_ssm_parameter("/app/customersupport/agentcore/client_secret", client_secret)
    put_ssm_parameter(
        "/app/customersupport/agentcore/cognito_discovery_url", discovery_url
    )

    return {"pool_id": pool_id, "client_id": client_id, "discovery_url": discovery_url}


def ensure_memory() -> str:
    memory_client = MemoryClient(region_name=_region())
    memory_name = "CustomerSupportMemory"
    strategies = [
        {
            StrategyType.USER_PREFERENCE.value: {
                "name": "CustomerPreferences",
                "description": "Captures customer preferences and behavior",
                "namespaces": ["support/customer/{actorId}/preferences/"],
            }
        },
        {
            StrategyType.SEMANTIC.value: {
                "name": "CustomerSupportSemantic",
                "description": "Stores facts from conversations",
                "namespaces": ["support/customer/{actorId}/semantic/"],
            }
        },
    ]

    try:
        memory_id = get_ssm_parameter("/app/customersupport/agentcore/memory_id")
        return memory_id
    except Exception:
        pass

    memory = memory_client.create_or_get_memory(
        name=memory_name,
        strategies=strategies,
        description="Customer support agent memory",
        event_expiry_days=90,
    )
    memory_id = memory["id"]
    put_ssm_parameter("/app/customersupport/agentcore/memory_id", memory_id)
    return memory_id


def ensure_gateway(cognito_config: Dict[str, str]) -> Dict[str, str]:
    gateway_client = boto3.client("bedrock-agentcore-control", region_name=_region())
    gateway_name = os.getenv("AGENTCORE_GATEWAY_NAME", "customersupport-gw")

    auth_config = {
        "customJWTAuthorizer": {
            "allowedClients": [cognito_config["client_id"]],
            "discoveryUrl": cognito_config["discovery_url"],
        }
    }

    try:
        create_response = gateway_client.create_gateway(
            name=gateway_name,
            roleArn=get_ssm_parameter("/app/customersupport/agentcore/gateway_iam_role"),
            protocolType="MCP",
            authorizerType="CUSTOM_JWT",
            authorizerConfiguration=auth_config,
            description="Customer Support AgentCore Gateway",
        )
        gateway = {
            "id": create_response["gatewayId"],
            "name": gateway_name,
            "gateway_url": create_response["gatewayUrl"],
            "gateway_arn": create_response["gatewayArn"],
        }
    except Exception:
        try:
            existing_id = get_ssm_parameter("/app/customersupport/agentcore/gateway_id")
            gateway_response = gateway_client.get_gateway(gatewayIdentifier=existing_id)
            gateway = {
                "id": existing_id,
                "name": gateway_response["name"],
                "gateway_url": gateway_response["gatewayUrl"],
                "gateway_arn": gateway_response["gatewayArn"],
            }
        except Exception:
            # Fallback: find by name
            gateways = gateway_client.list_gateways().get("items", [])
            match = next((g for g in gateways if g.get("name") == gateway_name), None)
            if not match:
                raise
            gateway = {
                "id": match["gatewayId"],
                "name": match["name"],
                "gateway_url": match["gatewayUrl"],
                "gateway_arn": match["gatewayArn"],
            }

    put_ssm_parameter("/app/customersupport/agentcore/gateway_id", gateway["id"])
    put_ssm_parameter("/app/customersupport/agentcore/gateway_name", gateway["name"])
    put_ssm_parameter("/app/customersupport/agentcore/gateway_arn", gateway["gateway_arn"])
    put_ssm_parameter("/app/customersupport/agentcore/gateway_url", gateway["gateway_url"])

    return gateway


def ensure_gateway_target(gateway_id: str) -> None:
    gateway_client = boto3.client("bedrock-agentcore-control", region_name=_region())

    existing = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id).get(
        "items", []
    )
    if any(item.get("name") == "LambdaUsingSDK" for item in existing):
        return

    api_spec_path = os.path.join(
        os.path.dirname(__file__), "..", "agentcore", "lambda", "api_spec.json"
    )
    with open(api_spec_path, "r", encoding="utf-8") as handle:
        api_spec = json.load(handle)

    lambda_target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": get_ssm_parameter(
                    "/app/customersupport/agentcore/lambda_arn"
                ),
                "toolSchema": {"inlinePayload": api_spec},
            }
        }
    }

    credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

    gateway_client.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name="LambdaUsingSDK",
        description="Lambda Target using SDK",
        targetConfiguration=lambda_target_config,
        credentialProviderConfigurations=credential_config,
    )


def create_agentcore_runtime_execution_role() -> str:
    iam = boto3.client("iam")
    region = _region()
    account_id = boto3.client("sts").get_caller_identity()["Account"]

    role_name = f"CustomerSupportAssistantBedrockAgentCoreRole-{region}"

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AssumeRolePolicy",
                "Effect": "Allow",
                "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"
                    },
                },
            }
        ],
    }

    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ECRImageAccess",
                "Effect": "Allow",
                "Action": ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                "Resource": [f"arn:aws:ecr:{region}:{account_id}:repository/*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:DescribeLogGroups"],
                "Resource": [f"arn:aws:logs:{region}:{account_id}:log-group:*"],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": [
                    f"arn:aws:logs:{region}:{account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ],
            },
            {
                "Sid": "ECRTokenAccess",
                "Effect": "Allow",
                "Action": ["ecr:GetAuthorizationToken"],
                "Resource": "*",
            },
            {
                "Effect": "Allow",
                "Action": [
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                "Resource": ["*"],
            },
            {
                "Effect": "Allow",
                "Resource": "*",
                "Action": "cloudwatch:PutMetricData",
                "Condition": {
                    "StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}
                },
            },
            {
                "Sid": "GetAgentAccessToken",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
                ],
                "Resource": [
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default",
                    f"arn:aws:bedrock-agentcore:{region}:{account_id}:workload-identity-directory/default/workload-identity/customer_support_agent-*",
                ],
            },
            {
                "Sid": "BedrockModelInvocation",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:ApplyGuardrail",
                    "bedrock:Retrieve",
                ],
                "Resource": [
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:{region}:{account_id}:*",
                    f"arn:aws:bedrock:*:{account_id}:inference-profile/*",
                ],
            },
            {
                "Sid": "AllowAgentToUseMemory",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:GetMemoryRecord",
                    "bedrock-agentcore:GetMemory",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                ],
                "Resource": [f"arn:aws:bedrock-agentcore:{region}:{account_id}:*"],
            },
            {
                "Sid": "GetMemoryId",
                "Effect": "Allow",
                "Action": ["ssm:GetParameter"],
                "Resource": [f"arn:aws:ssm:{region}:{account_id}:parameter/*"],
            },
            {
                "Sid": "GatewayAccess",
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:GetGateway", "bedrock-agentcore:InvokeGateway"],
                "Resource": [f"arn:aws:bedrock-agentcore:{region}:{account_id}:gateway/*"],
            },
        ],
    }

    try:
        role = iam.get_role(RoleName=role_name)["Role"]
        return role["Arn"]
    except iam.exceptions.NoSuchEntityException:
        pass

    role = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description="Execution role for AgentCore Runtime",
    )["Role"]

    iam.put_role_policy(
        RoleName=role_name,
        PolicyName=f"CustomerSupportAssistantBedrockAgentCorePolicy-{region}",
        PolicyDocument=json.dumps(policy_document),
    )

    time.sleep(5)
    return role["Arn"]


def deploy_runtime(memory_id: str, cognito_config: Dict[str, str], wait: bool) -> str:
    runtime = Runtime()
    region = _region()

    execution_role_arn = create_agentcore_runtime_execution_role()

    agent_name = os.getenv("AGENTCORE_AGENT_NAME", "awslegalpoc_customer_support")

    build_dir = Path(".agentcore_build")
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    # Copy runtime entrypoint + core package into isolated build context to avoid using root Dockerfile
    shutil.copy2("agentcore/runtime_app.py", build_dir / "runtime_app.py")
    shutil.copy2("agentcore/requirements.txt", build_dir / "requirements.txt")
    shutil.copytree("core", build_dir / "core")

    original_cwd = os.getcwd()
    os.chdir(build_dir)

    runtime.configure(
        entrypoint="runtime_app.py",
        execution_role=execution_role_arn,
        auto_create_ecr=True,
        requirements_file="requirements.txt",
        region=region,
        agent_name=agent_name,
        deployment_type="container",
        authorizer_configuration={
            "customJWTAuthorizer": {
                "allowedClients": [cognito_config["client_id"]],
                "discoveryUrl": cognito_config["discovery_url"],
            }
        },
        request_header_configuration={
            "requestHeaderAllowlist": [
                "Authorization",
                "X-Amzn-Bedrock-AgentCore-Runtime-Custom-H1",
            ]
        },
        memory_mode="STM_AND_LTM",
        disable_otel=True,  # Disable AgentCore default observability to use Langfuse
    )

    # Prepare Langfuse OTEL configuration if credentials are available
    env_vars = {
        "MEMORY_ID": memory_id,
        "BEDROCK_REGION": os.getenv("BEDROCK_REGION", region),
        "BEDROCK_MODEL_ID": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-2-lite-v1:0"),
        "BEDROCK_INFERENCE_PROFILE_ARN": os.getenv("BEDROCK_INFERENCE_PROFILE_ARN", ""),
    }

    # Add Langfuse observability configuration if credentials are provided
    langfuse_secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip('"')
    langfuse_public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip('"')
    langfuse_host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com").strip('"')

    if langfuse_secret_key and langfuse_public_key:
        # Create base64-encoded auth header for Langfuse OTEL endpoint
        langfuse_auth_token = base64.b64encode(
            f"{langfuse_public_key}:{langfuse_secret_key}".encode()
        ).decode()

        env_vars.update({
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"{langfuse_host}/api/public/otel",
            "OTEL_EXPORTER_OTLP_HEADERS": f"Authorization=Basic {langfuse_auth_token}",
            "DISABLE_ADOT_OBSERVABILITY": "true",
        })
        print(f"✅ Langfuse observability configured: {langfuse_host}")
    else:
        print("⚠️ Langfuse credentials not found - observability will not be enabled")

    launch_result = runtime.launch(
        env_vars=env_vars,
        auto_update_on_conflict=True,
    )

    os.chdir(original_cwd)

    runtime_arn = launch_result.agent_arn
    put_ssm_parameter("/app/customersupport/agentcore/runtime_arn", runtime_arn)

    if wait:
        status_response = runtime.status()
        status = status_response.endpoint["status"]
        end_status = {"READY", "CREATE_FAILED", "DELETE_FAILED", "UPDATE_FAILED"}

        while status not in end_status:
            print(f"Waiting for deployment... Current status: {status}")
            time.sleep(10)
            status_response = runtime.status()
            status = status_response.endpoint["status"]

        print(f"Final status: {status}")

    return runtime_arn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cognito-secret",
        default=os.getenv("COGNITO_CONFIG_SECRET", "awslegalpoc/cognito-config"),
    )
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    print(f"Using region: {_region()}")

    cognito_config = ensure_cognito_params(args.cognito_secret)
    memory_id = ensure_memory()
    gateway = ensure_gateway(cognito_config)
    ensure_gateway_target(gateway["id"])
    runtime_arn = deploy_runtime(memory_id, cognito_config, wait=args.wait)

    print("\n✅ AgentCore deployment complete")
    print(f"Memory ID: {memory_id}")
    print(f"Gateway URL: {gateway['gateway_url']}")
    print(f"Runtime ARN: {runtime_arn}")


if __name__ == "__main__":
    main()

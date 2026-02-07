import os
import boto3

from bedrock_agentcore_starter_toolkit.services.runtime import HttpBedrockAgentCoreClient

from core.config import AWS_REGION


def _resolve_region() -> str:
    return AWS_REGION or boto3.session.Session().region_name


def _get_ssm_parameter(name: str) -> str:
    region = _resolve_region()
    ssm = boto3.client("ssm", region_name=region)
    return ssm.get_parameter(Name=name, WithDecryption=False)["Parameter"]["Value"]


def get_runtime_arn() -> str:
    env = os.getenv("AGENTCORE_RUNTIME_ARN")
    if env:
        return env

    return _get_ssm_parameter("/app/customersupport/agentcore/runtime_arn")


def invoke_agentcore_runtime(
    prompt: str,
    bearer_token: str,
    session_id: str,
    actor_id: str,
) -> str:
    runtime_arn = get_runtime_arn()
    region = _resolve_region()

    client = HttpBedrockAgentCoreClient(region)
    response = client.invoke_endpoint(
        agent_arn=runtime_arn,
        payload={"prompt": prompt, "actor_id": actor_id},
        session_id=session_id,
        bearer_token=bearer_token,
        custom_headers={"Accept": "application/json"},
    )
    return response.get("response", "")

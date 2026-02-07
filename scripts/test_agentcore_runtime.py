import argparse
import os
import signal
import sys
import uuid
import urllib.parse

# Ensure repo root on path
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

import boto3
import requests
from bedrock_agentcore_starter_toolkit.services.runtime import get_data_plane_endpoint
from bedrock_agentcore_starter_toolkit.services.runtime import HttpBedrockAgentCoreClient

from core.cognito_auth import authenticate_user, get_or_create_cognito_config
from core.config import AWS_REGION, COGNITO_PASSWORD, COGNITO_USERNAME


def _region() -> str:
    return AWS_REGION or boto3.session.Session().region_name


def _get_runtime_arn() -> str:
    runtime_arn = os.getenv("AGENTCORE_RUNTIME_ARN")
    if runtime_arn:
        return runtime_arn
    ssm = boto3.client("ssm", region_name=_region())
    return ssm.get_parameter(Name="/app/customersupport/agentcore/runtime_arn")["Parameter"][
        "Value"
    ]

def _invoke_runtime_http(
    region: str,
    runtime_arn: str,
    token: str,
    payload: dict,
    session_id: str,
    timeout: int,
) -> dict:
    endpoint = get_data_plane_endpoint(region)
    url = f"{endpoint}/runtimes/{urllib.parse.quote(runtime_arn, safe='')}/invocations"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
        "Authorization": f"Bearer {token}",
    }
    response = requests.post(
        url,
        params={"qualifier": "DEFAULT"},
        headers=headers,
        json=payload,
        timeout=(10, timeout),
    )
    response.raise_for_status()
    if not response.content:
        return {}
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", default="List all of your tools")
    parser.add_argument("--actor-id", default="customer_001")
    parser.add_argument("--session-id")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--stream", action="store_true", help="Use streaming client")
    args = parser.parse_args()

    config = get_or_create_cognito_config()
    username = COGNITO_USERNAME or "admin"
    password = COGNITO_PASSWORD or "ChangeMe123!"
    token = authenticate_user(username, password, config)

    session_id = args.session_id or str(uuid.uuid4())
    runtime_arn = _get_runtime_arn()

    payload = {"prompt": args.prompt, "actor_id": args.actor_id}

    def _timeout_handler(signum, frame):
        raise TimeoutError("Request timed out")

    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(args.timeout)
    try:
        if args.stream:
            client = HttpBedrockAgentCoreClient(_region())
            response = client.invoke_endpoint(
                agent_arn=runtime_arn,
                payload=payload,
                session_id=session_id,
                bearer_token=token,
                custom_headers={"Accept": "application/json"},
            )
        else:
            response = _invoke_runtime_http(
                _region(),
                runtime_arn,
                token,
                payload,
                session_id,
                args.timeout,
            )
    finally:
        signal.alarm(0)

    print("Session ID:", session_id)
    print("Response:\n", response.get("response", ""))


if __name__ == "__main__":
    main()

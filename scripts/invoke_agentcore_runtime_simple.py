import base64
import hashlib
import hmac
import json
import os
import uuid
import urllib.parse

import boto3
import requests
from bedrock_agentcore_starter_toolkit.services.runtime import get_data_plane_endpoint

RUNTIME_ARN = os.getenv(
    "AGENTCORE_RUNTIME_ARN",
    "arn:aws:bedrock-agentcore:us-east-2:729665431827:runtime/awslegalpoc_customer_support-NmZatwFYo5",
)
REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-2"
COGNITO_SECRET_NAME = os.getenv("COGNITO_CONFIG_SECRET", "awslegalpoc/cognito-config")
USERNAME = os.getenv("COGNITO_USERNAME", "admin")
PASSWORD = os.getenv("COGNITO_PASSWORD", "ChangeMe123!")


def _secret_hash(username: str, client_id: str, client_secret: str) -> str:
    message = bytes(username + client_id, "utf-8")
    key = bytes(client_secret, "utf-8")
    return base64.b64encode(hmac.new(key, message, digestmod=hashlib.sha256).digest()).decode()


sm = boto3.client("secretsmanager", region_name=REGION)
secret = sm.get_secret_value(SecretId=COGNITO_SECRET_NAME)
cfg = json.loads(secret["SecretString"])

cognito = boto3.client("cognito-idp", region_name=REGION)
auth = cognito.initiate_auth(
    ClientId=cfg["client_id"],
    AuthFlow="USER_PASSWORD_AUTH",
    AuthParameters={
        "USERNAME": USERNAME,
        "PASSWORD": PASSWORD,
        "SECRET_HASH": _secret_hash(USERNAME, cfg["client_id"], cfg["client_secret"]),
    },
)
access_token = auth["AuthenticationResult"]["AccessToken"]
print("Authenticated. Token length:", len(access_token))

session_id = str(uuid.uuid4())
payload = {"prompt": "List all of your tools", "actor_id": "customer_001"}

endpoint = get_data_plane_endpoint(REGION)
url = f"{endpoint}/runtimes/{urllib.parse.quote(RUNTIME_ARN, safe='')}/invocations"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": session_id,
    "Authorization": f"Bearer {access_token}",
}

resp = requests.post(
    url,
    params={"qualifier": "DEFAULT"},
    headers=headers,
    json=payload,
    timeout=(10, 60),
)
resp.raise_for_status()

print("Session ID:", session_id)
if resp.content:
    print(resp.json().get("response", ""))
else:
    print("(no response body)")

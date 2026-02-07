import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from typing import Optional

import boto3

from core.config import AWS_REGION


@dataclass
class CognitoConfig:
    pool_id: str
    client_id: str
    client_secret: str


def _secret_hash(username: str, client_id: str, client_secret: str) -> str:
    message = bytes(username + client_id, "utf-8")
    key = bytes(client_secret, "utf-8")
    return base64.b64encode(
        hmac.new(key, message, digestmod=hashlib.sha256).digest()
    ).decode()


def _region() -> str:
    return AWS_REGION or boto3.session.Session().region_name


def _secrets_client():
    return boto3.client("secretsmanager", region_name=_region())


def _cognito_client():
    return boto3.client("cognito-idp", region_name=_region())


def _get_config_secret(secret_name: str) -> Optional[dict]:
    sm = _secrets_client()
    try:
        response = sm.get_secret_value(SecretId=secret_name)
        return json.loads(response["SecretString"])
    except Exception:
        return None


def get_or_create_cognito_config() -> CognitoConfig:
    secret_name = os.getenv("COGNITO_CONFIG_SECRET", "awslegalpoc/cognito-config")
    existing = _get_config_secret(secret_name)
    if existing and all(k in existing for k in ("pool_id", "client_id", "client_secret")):
        return CognitoConfig(
            pool_id=existing["pool_id"],
            client_id=existing["client_id"],
            client_secret=existing["client_secret"],
        )

    raise RuntimeError(
        "Cognito config secret not found. Run scripts/bootstrap_cognito.sh first."
    )


def ensure_user(username: str, password: str, config: CognitoConfig) -> None:
    cognito = _cognito_client()
    try:
        cognito.admin_create_user(
            UserPoolId=config.pool_id,
            Username=username,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
        )
        cognito.admin_set_user_password(
            UserPoolId=config.pool_id,
            Username=username,
            Password=password,
            Permanent=True,
        )
    except cognito.exceptions.UsernameExistsException:
        pass


def authenticate_user(username: str, password: str, config: CognitoConfig) -> str:
    cognito = _cognito_client()
    secret_hash = _secret_hash(username, config.client_id, config.client_secret)

    auth = cognito.initiate_auth(
        ClientId=config.client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": username,
            "PASSWORD": password,
            "SECRET_HASH": secret_hash,
        },
    )
    return auth["AuthenticationResult"]["AccessToken"]

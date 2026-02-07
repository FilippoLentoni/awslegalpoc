import base64
import hashlib
import hmac
import json
import os

import boto3


def secret_hash(username: str, client_id: str, client_secret: str) -> str:
    message = bytes(username + client_id, "utf-8")
    key = bytes(client_secret, "utf-8")
    return base64.b64encode(hmac.new(key, message, digestmod=hashlib.sha256).digest()).decode()


def main() -> None:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise SystemExit("AWS_REGION or AWS_DEFAULT_REGION must be set")

    username = os.getenv("COGNITO_USERNAME", "admin")
    password = os.getenv("COGNITO_PASSWORD", "ChangeMe123!")
    secret_name = os.getenv("COGNITO_CONFIG_SECRET", "awslegalpoc/cognito-config")

    pool_name = os.getenv("COGNITO_POOL_NAME", "awslegalpoc-temp-pool")
    client_name = os.getenv("COGNITO_CLIENT_NAME", "awslegalpoc-temp-client")

    cognito = boto3.client("cognito-idp", region_name=region)
    secrets = boto3.client("secretsmanager", region_name=region)

    # Create pool
    pool = cognito.create_user_pool(
        PoolName=pool_name,
        Policies={"PasswordPolicy": {"MinimumLength": 8}},
        AutoVerifiedAttributes=[],
    )
    pool_id = pool["UserPool"]["Id"]

    # Create client
    client = cognito.create_user_pool_client(
        UserPoolId=pool_id,
        ClientName=client_name,
        GenerateSecret=True,
        ExplicitAuthFlows=[
            "ALLOW_USER_PASSWORD_AUTH",
            "ALLOW_REFRESH_TOKEN_AUTH",
            "ALLOW_USER_SRP_AUTH",
        ],
    )

    client_id = client["UserPoolClient"]["ClientId"]
    client_secret = client["UserPoolClient"]["ClientSecret"]

    # Create user + set password
    try:
        cognito.admin_create_user(
            UserPoolId=pool_id,
            Username=username,
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
        )
        cognito.admin_set_user_password(
            UserPoolId=pool_id,
            Username=username,
            Password=password,
            Permanent=True,
        )
    except cognito.exceptions.UsernameExistsException:
        pass

    # Verify auth works
    auth = cognito.initiate_auth(
        ClientId=client_id,
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": username,
            "PASSWORD": password,
            "SECRET_HASH": secret_hash(username, client_id, client_secret),
        },
    )

    if "AuthenticationResult" not in auth:
        raise SystemExit("Authentication failed during bootstrap")

    payload = {
        "pool_id": pool_id,
        "client_id": client_id,
        "client_secret": client_secret,
    }

    try:
        secrets.create_secret(Name=secret_name, SecretString=json.dumps(payload))
    except secrets.exceptions.ResourceExistsException:
        secrets.update_secret(SecretId=secret_name, SecretString=json.dumps(payload))

    print("Bootstrap complete")
    print(f"User pool: {pool_id}")
    print(f"Client id: {client_id}")
    print(f"Secret: {secret_name}")


if __name__ == "__main__":
    main()

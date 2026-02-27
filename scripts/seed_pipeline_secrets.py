"""Seed pipeline secrets into AWS Secrets Manager from config/secrets.json.

Creates (or updates) a {stackPrefix}/pipeline-secrets secret in the
target account so that CodeBuild can retrieve credentials at build time.

Usage:
    python scripts/seed_pipeline_secrets.py --env beta
    python scripts/seed_pipeline_secrets.py --env prod
"""

import argparse
import json
import os
from pathlib import Path

import boto3


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed pipeline secrets into Secrets Manager")
    parser.add_argument("--env", required=True, help="Environment name (must exist in environments.json)")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent

    # Load environment config
    env_config_path = project_root / "config" / "environments.json"
    with open(env_config_path) as f:
        all_config = json.load(f)

    if args.env not in all_config:
        raise SystemExit(f"Environment '{args.env}' not found. Available: {[k for k in all_config if k != 'github']}")

    config = all_config[args.env]
    stack_prefix = config["stackPrefix"]
    region = config["region"]

    # Load secrets
    secrets_path = project_root / "config" / "secrets.json"
    if not secrets_path.exists():
        raise SystemExit(f"Secrets file not found: {secrets_path}\nCopy config/secrets.example.json to config/secrets.json and fill in values.")

    with open(secrets_path) as f:
        all_secrets = json.load(f)

    if args.env not in all_secrets:
        raise SystemExit(f"Environment '{args.env}' not found in secrets.json")

    env_secrets = all_secrets[args.env]

    # Build the pipeline secrets payload
    pipeline_secrets = {
        "cognito_password": env_secrets.get("cognito", {}).get("password", ""),
        "langfuse_public_key": env_secrets.get("langfuse", {}).get("publicKey", ""),
        "langfuse_secret_key": env_secrets.get("langfuse", {}).get("secretKey", ""),
    }

    secret_name = f"{stack_prefix}/pipeline-secrets"
    client = boto3.client("secretsmanager", region_name=region)

    try:
        client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(pipeline_secrets),
            Description=f"Pipeline secrets for {args.env} environment",
        )
        print(f"Created secret: {secret_name}")
    except client.exceptions.ResourceExistsException:
        client.update_secret(
            SecretId=secret_name,
            SecretString=json.dumps(pipeline_secrets),
        )
        print(f"Updated secret: {secret_name}")

    print(f"  Region: {region}")
    print(f"  Keys: {list(pipeline_secrets.keys())}")


if __name__ == "__main__":
    main()

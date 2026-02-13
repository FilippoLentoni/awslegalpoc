#!/usr/bin/env python3
import json
import os
from pathlib import Path

import aws_cdk as cdk

from ecr_stack import AwsLegalPocEcrStack
from app_stack import AwsLegalPocAppStack
from agentcore_stack import AwsLegalPocAgentCoreStack


# Load environment configuration
def load_config(env: str):
    config_path = Path(__file__).parent.parent / "config" / "environments.json"
    with open(config_path) as f:
        config = json.load(f)
    if env not in config:
        raise ValueError(f"Environment '{env}' not found in config. Available: {list(config.keys())}")
    return config[env]


app = cdk.App()

# Get environment from context (passed via --context env=beta)
env_name = app.node.try_get_context("env") or os.getenv("DEPLOY_ENV", "beta")
config = load_config(env_name)

account = config["account"]
region = config["region"]
stack_prefix = config["stackPrefix"]

print(f"Deploying to environment: {env_name}")
print(f"Account: {account}, Region: {region}")
print(f"Stack prefix: {stack_prefix}")

ecr_stack = AwsLegalPocEcrStack(
    app,
    f"{stack_prefix}-EcrStack",
    env=cdk.Environment(account=account, region=region),
    env_name=env_name,
    config=config,
)

AwsLegalPocAppStack(
    app,
    f"{stack_prefix}-AppStack",
    repo=ecr_stack.repo,
    env=cdk.Environment(account=account, region=region),
    env_name=env_name,
    config=config,
)

AwsLegalPocAgentCoreStack(
    app,
    f"{stack_prefix}-AgentCoreStack",
    env=cdk.Environment(account=account, region=region),
    env_name=env_name,
    config=config,
)

app.synth()

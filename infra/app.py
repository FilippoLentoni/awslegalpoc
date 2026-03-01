#!/usr/bin/env python3
import json
import os
from pathlib import Path

import aws_cdk as cdk

from ecr_stack import AwsLegalPocEcrStack
from app_stack import AwsLegalPocAppStack
from agentcore_stack import AwsLegalPocAgentCoreStack
from knowledge_base_stack import AwsLegalPocKnowledgeBaseStack
from pipeline_stack import AwsLegalPocPipelineStack
from cross_account_role_stack import AwsLegalPocCrossAccountRoleStack


# Load environment configuration
def load_config(env: str):
    config_path = Path(__file__).parent.parent / "config" / "environments.json"
    with open(config_path) as f:
        all_config = json.load(f)
    if env not in all_config:
        raise ValueError(f"Environment '{env}' not found in config. Available: {list(all_config.keys())}")
    return all_config[env], all_config


app = cdk.App()

# Get environment from context (passed via --context env=beta)
env_name = app.node.try_get_context("env") or os.getenv("DEPLOY_ENV", "beta")
config, all_config = load_config(env_name)

account = config["account"]
region = config["region"]
stack_prefix = config["stackPrefix"]

print(f"Deploying to environment: {env_name}")
print(f"Account: {account}, Region: {region}")
print(f"Stack prefix: {stack_prefix}")

# Application stacks (only in beta and prod, not orchestrator)
if env_name in ("beta", "prod"):
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

    AwsLegalPocKnowledgeBaseStack(
        app,
        f"{stack_prefix}-KnowledgeBaseStack",
        env=cdk.Environment(account=account, region=region),
        env_name=env_name,
        config=config,
    )

# Pipeline stack (only in orchestrator account, where CI/CD pipeline lives)
if env_name == "orchestrator":
    AwsLegalPocPipelineStack(
        app,
        f"{stack_prefix}-PipelineStack",
        env=cdk.Environment(account=account, region=region),
        env_name=env_name,
        config=config,
    )

# Cross-account role stack (deployed in beta and prod, trusts the orchestrator account)
if env_name in ("beta", "prod") and "orchestrator" in all_config:
    orchestrator_account = all_config["orchestrator"]["account"]
    AwsLegalPocCrossAccountRoleStack(
        app,
        f"{stack_prefix}-CrossAccountRoleStack",
        env=cdk.Environment(account=account, region=region),
        env_name=env_name,
        config=config,
        trusted_account=orchestrator_account,
    )

app.synth()

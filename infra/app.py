#!/usr/bin/env python3
import os

import aws_cdk as cdk

from ecr_stack import AwsLegalPocEcrStack
from app_stack import AwsLegalPocAppStack
from agentcore_stack import AwsLegalPocAgentCoreStack


app = cdk.App()

account = os.getenv("CDK_DEFAULT_ACCOUNT")
region = os.getenv("CDK_DEFAULT_REGION")

if not account or not region:
    raise ValueError("CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION must be set")

ecr_stack = AwsLegalPocEcrStack(
    app,
    "AwsLegalPocEcrStack",
    env=cdk.Environment(account=account, region=region),
)

AwsLegalPocAppStack(
    app,
    "AwsLegalPocAppStack",
    repo=ecr_stack.repo,
    env=cdk.Environment(account=account, region=region),
)

AwsLegalPocAgentCoreStack(
    app,
    "AwsLegalPocAgentCoreStack",
    env=cdk.Environment(account=account, region=region),
)

app.synth()

"""Lightweight stack deployed in the prod account to allow cross-account deployment.

The CodeBuild role in the beta account assumes this role to deploy to prod.
Deploy once: cdk deploy {stackPrefix}-CrossAccountRoleStack --context env=prod
"""

from aws_cdk import Duration, Stack, Tags
from aws_cdk import aws_iam as iam
from constructs import Construct


class AwsLegalPocCrossAccountRoleStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        config: dict,
        beta_account: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack_prefix = config["stackPrefix"]

        # Role that CodeBuild in the beta account can assume
        deploy_role = iam.Role(
            self,
            "CrossAccountDeployRole",
            role_name=f"{stack_prefix}-CrossAccountDeployRole",
            assumed_by=iam.AccountPrincipal(beta_account),
            max_session_duration=Duration.hours(1),
        )

        # Broad deployment permissions (CDK, ECS, ECR, Bedrock, etc.)
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudformation:*",
                    "ecr:*",
                    "ecs:*",
                    "ec2:*",
                    "iam:*",
                    "s3:*",
                    "ssm:*",
                    "secretsmanager:*",
                    "logs:*",
                    "elasticloadbalancingv2:*",
                    "bedrock:*",
                    "bedrock-agentcore:*",
                    "codebuild:*",
                    "cognito-idp:*",
                    "s3vectors:*",
                    "xray:*",
                    "cloudwatch:*",
                    "application-autoscaling:*",
                    "servicediscovery:*",
                    "sns:*",
                    "sts:GetCallerIdentity",
                ],
                resources=["*"],
            )
        )

        # Apply tags
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

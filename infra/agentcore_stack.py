from aws_cdk import Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class AwsLegalPocAgentCoreStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Gateway IAM role used by agentcore_deploy.py when creating the gateway
        gateway_role = iam.Role(
            self,
            "GatewayAgentCoreRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        )

        ssm.StringParameter(
            self,
            "GatewayAgentcoreIAMRoleParam",
            parameter_name="/app/customersupport/agentcore/gateway_iam_role",
            string_value=gateway_role.role_arn,
        )

        # Apply tags from config
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

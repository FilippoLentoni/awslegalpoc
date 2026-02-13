from aws_cdk import Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
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

        warranty_table = dynamodb.Table(
            self,
            "WarrantyTable",
            partition_key=dynamodb.Attribute(
                name="serial_number", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        customer_profile_table = dynamodb.Table(
            self,
            "CustomerProfileTable",
            partition_key=dynamodb.Attribute(
                name="customer_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        ssm.StringParameter(
            self,
            "WarrantyTableNameParam",
            parameter_name="/app/customersupport/dynamodb/warranty_table_name",
            string_value=warranty_table.table_name,
        )

        ssm.StringParameter(
            self,
            "CustomerProfileTableNameParam",
            parameter_name="/app/customersupport/dynamodb/customer_profile_table_name",
            string_value=customer_profile_table.table_name,
        )

        ddgs_layer = lambda_.LayerVersion(
            self,
            "DdgsLayer",
            code=lambda_.Code.from_asset("../agentcore/lambda/ddgs-layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="DDGS package for Lambda functions",
        )

        lambda_role = iam.Role(
            self,
            "CustomerSupportLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        warranty_table.grant_read_data(lambda_role)
        customer_profile_table.grant_read_data(lambda_role)
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ssm:GetParameter"],
                resources=[f"arn:aws:ssm:{Stack.of(self).region}:{Stack.of(self).account}:parameter/app/customersupport/*"],
            )
        )

        lambda_fn = lambda_.Function(
            self,
            "CustomerSupportLambda",
            description="Lambda function for Customer Support Assistant",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="lambda_function.lambda_handler",
            code=lambda_.Code.from_asset("../agentcore/lambda/python"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=512,
            layers=[ddgs_layer],
        )

        gateway_role = iam.Role(
            self,
            "GatewayAgentCoreRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        )

        gateway_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[lambda_fn.function_arn],
            )
        )

        ssm.StringParameter(
            self,
            "GatewayAgentcoreIAMRoleParam",
            parameter_name="/app/customersupport/agentcore/gateway_iam_role",
            string_value=gateway_role.role_arn,
        )

        ssm.StringParameter(
            self,
            "LambdaArnParam",
            parameter_name="/app/customersupport/agentcore/lambda_arn",
            string_value=lambda_fn.function_arn,
        )

        # Apply tags from config
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

import os

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, SecretValue, Tags
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class AwsLegalPocAppStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        repo: ecr.IRepository,
        env_name: str,
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        acm_cert_arn = os.getenv("ACM_CERT_ARN")
        enable_alb_cognito = os.getenv("ENABLE_ALB_COGNITO", "false").lower() == "true"
        if enable_alb_cognito and not acm_cert_arn:
            raise ValueError("ACM_CERT_ARN env var is required for HTTPS + Cognito")

        cognito_domain_prefix = os.getenv("COGNITO_DOMAIN_PREFIX")
        if not cognito_domain_prefix:
            # Default to environment-aware prefix
            cognito_domain_prefix = f"{config['stackPrefix']}-{Stack.of(self).account}"

        # Use config values with environment variable fallback
        langfuse_host = os.getenv("LANGFUSE_HOST", config.get("langfuseHost", "https://cloud.langfuse.com"))
        bedrock_region = os.getenv("BEDROCK_REGION", config.get("region", Stack.of(self).region))
        bedrock_model_id = os.getenv("BEDROCK_MODEL_ID", config.get("bedrockModelId", "amazon.nova-2-lite-v1:0"))
        bedrock_inference_profile_arn = os.getenv("BEDROCK_INFERENCE_PROFILE_ARN", config.get("bedrockInferenceProfile"))
        app_version = os.getenv("APP_VERSION", env_name)

        # KB config from SSM (set by KnowledgeBaseStack)
        stack_prefix = config["stackPrefix"]
        ssm_prefix = f"/app/{stack_prefix}/kb"
        kb_id = ssm.StringParameter.value_for_string_parameter(
            self, f"{ssm_prefix}/knowledge-base-id"
        )
        kb_data_bucket = ssm.StringParameter.value_for_string_parameter(
            self, f"{ssm_prefix}/data-bucket-name"
        )
        kb_data_source_id = ssm.StringParameter.value_for_string_parameter(
            self, f"{ssm_prefix}/data-source-id"
        )

        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
        )

        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:*",
                    "bedrock-agentcore:*",
                    "secretsmanager:GetSecretValue",
                    "ssm:GetParameter",
                ],
                resources=["*"],
            )
        )

        # S3 permissions for KB document management from the UI
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:ListBucket"],
                resources=[f"arn:aws:s3:::{stack_prefix}-kb-data"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                resources=[f"arn:aws:s3:::{stack_prefix}-kb-data/*"],
            )
        )

        task_def = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            cpu=512,
            memory_limit_mib=1024,
            task_role=task_role,
        )

        log_group = logs.LogGroup(
            self,
            "AppLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        langfuse_secret = secretsmanager.Secret(
            self,
            "LangfuseKeys",
            secret_name=f"{config['stackPrefix']}/langfuse",
            secret_string_value=SecretValue.unsafe_plain_text(
                '{\"public_key\":\"CHANGEME\",\"secret_key\":\"CHANGEME\"}'
            ),
        )

        container = task_def.add_container(
            "StreamlitContainer",
            image=ecs.ContainerImage.from_ecr_repository(repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix=config['stackPrefix'], log_group=log_group),
            environment={
                "AWS_REGION": Stack.of(self).region,
                "BEDROCK_REGION": bedrock_region,
                "BEDROCK_MODEL_ID": bedrock_model_id,
                "BEDROCK_INFERENCE_PROFILE_ARN": bedrock_inference_profile_arn or "",
                "LANGFUSE_HOST": langfuse_host,
                "COGNITO_ENABLED": "true",
                "COGNITO_CONFIG_SECRET": f"{config['stackPrefix']}/cognito-config",
                "APP_VERSION": app_version,
                "KNOWLEDGE_BASE_ID": kb_id,
                "KB_DATA_BUCKET_NAME": kb_data_bucket,
                "KB_DATA_SOURCE_ID": kb_data_source_id,
            },
            secrets={
                "LANGFUSE_PUBLIC_KEY": ecs.Secret.from_secrets_manager(
                    langfuse_secret, "public_key"
                ),
                "LANGFUSE_SECRET_KEY": ecs.Secret.from_secrets_manager(
                    langfuse_secret, "secret_key"
                ),
            },
        )

        container.add_port_mappings(ecs.PortMapping(container_port=8501))

        service_sg = ec2.SecurityGroup(self, "ServiceSG", vpc=vpc)
        alb_sg = ec2.SecurityGroup(self, "AlbSG", vpc=vpc)

        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        service_sg.add_ingress_rule(alb_sg, ec2.Port.tcp(8501))

        service = ecs.FargateService(
            self,
            "Service",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            assign_public_ip=True,
            security_groups=[service_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
        )

        http_listener = alb.add_listener("Http", port=80, open=True)

        if enable_alb_cognito and acm_cert_arn:
            target_group = elbv2.ApplicationTargetGroup(
                self,
                "TargetGroup",
                vpc=vpc,
                port=8501,
                protocol=elbv2.ApplicationProtocol.HTTP,
                targets=[service],
                health_check=elbv2.HealthCheck(path="/"),
            )

            http_listener.add_action(
                "HttpRedirect",
                action=elbv2.ListenerAction.redirect(
                    protocol="HTTPS",
                    port="443",
                    permanent=True,
                ),
            )

            certificate = acm.Certificate.from_certificate_arn(
                self, "AlbCert", acm_cert_arn
            )

            https_listener = alb.add_listener(
                "Https",
                port=443,
                certificates=[certificate],
                open=True,
            )

            user_pool = cognito.UserPool(
                self,
                "UserPool",
                self_sign_up_enabled=False,
                sign_in_aliases=cognito.SignInAliases(email=True),
            )

            user_pool_client = cognito.UserPoolClient(
                self,
                "UserPoolClient",
                user_pool=user_pool,
                generate_secret=True,
                auth_flows=cognito.AuthFlow(user_password=True),
            )

            user_pool_domain = cognito.UserPoolDomain(
                self,
                "UserPoolDomain",
                user_pool=user_pool,
                cognito_domain=cognito.CognitoDomainOptions(
                    domain_prefix=cognito_domain_prefix
                ),
            )

            https_listener.add_action(
                "Authenticate",
                action=elbv2.ListenerAction.authenticate_cognito(
                    user_pool=user_pool,
                    user_pool_client=user_pool_client,
                    user_pool_domain=user_pool_domain,
                    next=elbv2.ListenerAction.forward([target_group]),
                ),
            )
        else:
            http_listener.add_targets(
                "HttpTargets",
                protocol=elbv2.ApplicationProtocol.HTTP,
                port=8501,
                targets=[service],
                health_check=elbv2.HealthCheck(path="/"),
            )

        scalable_target = service.auto_scale_task_count(min_capacity=1, max_capacity=2)
        scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=60,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(60),
        )

        CfnOutput(self, "AlbUrl", value=f"http://{alb.load_balancer_dns_name}")
        if enable_alb_cognito and acm_cert_arn:
            CfnOutput(self, "CognitoUserPoolId", value=user_pool.user_pool_id)
            CfnOutput(self, "CognitoClientId", value=user_pool_client.user_pool_client_id)
            CfnOutput(self, "CognitoDomain", value=user_pool_domain.domain_name)
        CfnOutput(self, "EcsServiceName", value=service.service_name)
        CfnOutput(self, "EcrRepoUri", value=repo.repository_uri)

        # Apply tags from config
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

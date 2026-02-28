import json
from pathlib import Path

from aws_cdk import RemovalPolicy, Stack, Tags
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as actions
from aws_cdk import aws_codestarconnections as codestar
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from constructs import Construct


class AwsLegalPocPipelineStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        config: dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        stack_prefix = config["stackPrefix"]

        # Load full config for prod and github settings
        config_path = Path(__file__).parent.parent / "config" / "environments.json"
        with open(config_path) as f:
            all_config = json.load(f)
        prod_config = all_config.get("prod", {})
        github_config = all_config.get("github", {})
        prod_account = prod_config.get("account", "")
        prod_region = prod_config.get("region", config["region"])

        # --- GitHub Connection ---
        # After deployment, approve this connection in the AWS Console:
        # Developer Tools > Settings > Connections
        connection = codestar.CfnConnection(
            self,
            "GitHubConnection",
            connection_name=f"{stack_prefix}-github",
            provider_type="GitHub",
        )

        # --- Artifact Bucket ---
        artifact_bucket = s3.Bucket(
            self,
            "PipelineArtifacts",
            bucket_name=f"{stack_prefix}-pipeline-artifacts",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- CodeBuild IAM Role (shared by beta deploy + eval) ---
        build_role = iam.Role(
            self,
            "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        # Broad permissions needed for CDK deploy, ECS, ECR, Bedrock, etc.
        build_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudformation:*",
                    "codebuild:*",
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

        # Allow assuming cross-account role for prod deployments
        if prod_account:
            build_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["sts:AssumeRole"],
                    resources=[
                        f"arn:aws:iam::{prod_account}:role/{prod_config.get('stackPrefix', 'awslegalpoc')}-CrossAccountDeployRole"
                    ],
                )
            )

        # --- Secrets ARN for buildspec env injection ---
        beta_secrets_arn = f"arn:aws:secretsmanager:{config['region']}:{config['account']}:secret:{stack_prefix}/pipeline-secrets"

        # --- CodeBuild: Deploy Beta ---
        deploy_buildspec = {
            "version": "0.2",
            "phases": {
                "install": {
                    "runtime-versions": {"python": "3.11", "nodejs": "18"},
                    "commands": [
                        "npm install -g aws-cdk",
                        "pip install poetry",
                        "poetry install --no-interaction --no-root",
                    ],
                },
                "pre_build": {
                    "commands": [
                        "echo 'Generating secrets file from environment variables...'",
                        "python scripts/generate_secrets_from_env.py",
                        "echo 'Verifying AWS credentials...'",
                        "aws sts get-caller-identity",
                    ],
                },
                "build": {
                    "commands": [
                        "echo \"Deploying to ${DEPLOY_ENV}...\"",
                        "chmod +x scripts/deploy-all.sh scripts/build.sh scripts/push.sh",
                        "./scripts/deploy-all.sh --env ${DEPLOY_ENV} --skip-tests",
                    ],
                },
                "post_build": {
                    "commands": ["echo \"Deployment to ${DEPLOY_ENV} complete\""],
                },
            },
        }

        beta_deploy_project = codebuild.Project(
            self,
            "BetaDeployProject",
            project_name=f"{stack_prefix}-deploy-beta",
            role=build_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                privileged=True,  # Required for Docker builds
                compute_type=codebuild.ComputeType.MEDIUM,
            ),
            build_spec=codebuild.BuildSpec.from_object(deploy_buildspec),
            environment_variables={
                "DEPLOY_ENV": codebuild.BuildEnvironmentVariable(
                    value="beta",
                ),
                "STACK_PREFIX": codebuild.BuildEnvironmentVariable(
                    value=stack_prefix,
                ),
                "COGNITO_PASSWORD": codebuild.BuildEnvironmentVariable(
                    value=f"{beta_secrets_arn}:cognito_password",
                    type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER,
                ),
                "LANGFUSE_PUBLIC_KEY": codebuild.BuildEnvironmentVariable(
                    value=f"{beta_secrets_arn}:langfuse_public_key",
                    type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER,
                ),
                "LANGFUSE_SECRET_KEY": codebuild.BuildEnvironmentVariable(
                    value=f"{beta_secrets_arn}:langfuse_secret_key",
                    type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER,
                ),
            },
        )

        # --- CodeBuild: Eval Tests ---
        eval_buildspec = {
            "version": "0.2",
            "phases": {
                "install": {
                    "runtime-versions": {"python": "3.11"},
                    "commands": [
                        "pip install poetry",
                        "poetry install --no-interaction --no-root",
                    ],
                },
                "build": {
                    "commands": [
                        "echo \"Running evaluation tests against ${DEPLOY_ENV}...\"",
                        "chmod +x scripts/deploy-all.sh",
                        "./scripts/deploy-all.sh --env ${DEPLOY_ENV} --skip-bootstrap --skip-cdk --skip-docker --skip-agentcore",
                    ],
                },
            },
        }

        eval_project = codebuild.Project(
            self,
            "EvalProject",
            project_name=f"{stack_prefix}-eval",
            role=build_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                compute_type=codebuild.ComputeType.MEDIUM,
            ),
            build_spec=codebuild.BuildSpec.from_object(eval_buildspec),
            environment_variables={
                "DEPLOY_ENV": codebuild.BuildEnvironmentVariable(
                    value="beta",
                ),
                "STACK_PREFIX": codebuild.BuildEnvironmentVariable(
                    value=stack_prefix,
                ),
                "COGNITO_PASSWORD": codebuild.BuildEnvironmentVariable(
                    value=f"{beta_secrets_arn}:cognito_password",
                    type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER,
                ),
                "LANGFUSE_PUBLIC_KEY": codebuild.BuildEnvironmentVariable(
                    value=f"{beta_secrets_arn}:langfuse_public_key",
                    type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER,
                ),
                "LANGFUSE_SECRET_KEY": codebuild.BuildEnvironmentVariable(
                    value=f"{beta_secrets_arn}:langfuse_secret_key",
                    type=codebuild.BuildEnvironmentVariableType.SECRETS_MANAGER,
                ),
            },
        )

        # --- CodeBuild: Deploy Prod (cross-account) ---
        prod_deploy_project = None
        if prod_account:
            prod_stack_prefix = prod_config.get("stackPrefix", "awslegalpoc")
            prod_secrets_name = f"{prod_stack_prefix}/pipeline-secrets"

            prod_deploy_project = codebuild.Project(
                self,
                "ProdDeployProject",
                project_name=f"{stack_prefix}-deploy-prod",
                role=build_role,
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.AMAZON_LINUX_2_5,
                    privileged=True,
                    compute_type=codebuild.ComputeType.MEDIUM,
                ),
                build_spec=codebuild.BuildSpec.from_object({
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {"python": "3.11", "nodejs": "18"},
                            "commands": [
                                "npm install -g aws-cdk",
                                "pip install poetry",
                                "poetry install --no-interaction --no-root",
                            ],
                        },
                        "pre_build": {
                            "commands": [
                                # Assume cross-account role for prod
                                f'CREDS=$(aws sts assume-role --role-arn "arn:aws:iam::{prod_account}:role/{prod_stack_prefix}-CrossAccountDeployRole" --role-session-name "codebuild-prod-deploy" --output json)',
                                'export AWS_ACCESS_KEY_ID=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)[\'Credentials\'][\'AccessKeyId\'])")',
                                'export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)[\'Credentials\'][\'SecretAccessKey\'])")',
                                'export AWS_SESSION_TOKEN=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)[\'Credentials\'][\'SessionToken\'])")',
                                "aws sts get-caller-identity",
                                # Fetch secrets from prod account (after assume-role)
                                f'PROD_SECRETS=$(aws secretsmanager get-secret-value --secret-id "{prod_secrets_name}" --query SecretString --output text)',
                                "export COGNITO_PASSWORD=$(echo $PROD_SECRETS | python3 -c \"import sys,json; print(json.load(sys.stdin)['cognito_password'])\")",
                                "export LANGFUSE_PUBLIC_KEY=$(echo $PROD_SECRETS | python3 -c \"import sys,json; print(json.load(sys.stdin)['langfuse_public_key'])\")",
                                "export LANGFUSE_SECRET_KEY=$(echo $PROD_SECRETS | python3 -c \"import sys,json; print(json.load(sys.stdin)['langfuse_secret_key'])\")",
                                "python scripts/generate_secrets_from_env.py",
                            ],
                        },
                        "build": {
                            "commands": [
                                "chmod +x scripts/deploy-all.sh scripts/build.sh scripts/push.sh",
                                "./scripts/deploy-all.sh --env prod --skip-tests",
                            ],
                        },
                        "post_build": {
                            "commands": ["echo 'Production deployment complete'"],
                        },
                    },
                }),
                environment_variables={
                    "DEPLOY_ENV": codebuild.BuildEnvironmentVariable(value="prod"),
                    "STACK_PREFIX": codebuild.BuildEnvironmentVariable(value=prod_stack_prefix),
                },
            )

        # --- SNS Topic for Approval Notifications ---
        approval_topic = sns.Topic(
            self,
            "ApprovalTopic",
            topic_name=f"{stack_prefix}-pipeline-approval",
        )

        # --- CodePipeline ---
        source_output = codepipeline.Artifact("SourceOutput")

        pipeline = codepipeline.Pipeline(
            self,
            "Pipeline",
            pipeline_name=f"{stack_prefix}-pipeline",
            artifact_bucket=artifact_bucket,
            stages=[
                # Stage 1: Source
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        actions.CodeStarConnectionsSourceAction(
                            action_name="GitHub",
                            connection_arn=connection.attr_connection_arn,
                            owner=github_config.get("owner", "OWNER"),
                            repo=github_config.get("repo", "REPO"),
                            branch="main",
                            output=source_output,
                            trigger_on_push=True,
                        ),
                    ],
                ),
                # Stage 2: Deploy Beta
                codepipeline.StageProps(
                    stage_name="DeployBeta",
                    actions=[
                        actions.CodeBuildAction(
                            action_name="DeployBeta",
                            project=beta_deploy_project,
                            input=source_output,
                        ),
                    ],
                ),
                # Stage 3: Eval Tests
                codepipeline.StageProps(
                    stage_name="EvalTests",
                    actions=[
                        actions.CodeBuildAction(
                            action_name="RunEval",
                            project=eval_project,
                            input=source_output,
                        ),
                    ],
                ),
                # Stage 4: Manual Approval
                codepipeline.StageProps(
                    stage_name="Approval",
                    actions=[
                        actions.ManualApprovalAction(
                            action_name="ApproveForProd",
                            notification_topic=approval_topic,
                            additional_information="Beta deployment and eval tests passed. Approve to deploy to production.",
                        ),
                    ],
                ),
            ],
        )

        # Stage 5: Deploy Prod (only if prod account is configured)
        if prod_deploy_project:
            pipeline.add_stage(
                stage_name="DeployProd",
                actions=[
                    actions.CodeBuildAction(
                        action_name="DeployProd",
                        project=prod_deploy_project,
                        input=source_output,
                    ),
                ],
            )

        # Apply tags
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

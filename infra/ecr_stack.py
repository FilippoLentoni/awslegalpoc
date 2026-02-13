from aws_cdk import Stack, Tags
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class AwsLegalPocEcrStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str,
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.repo = ecr.Repository(
            self,
            "StreamlitRepo",
            repository_name=config["ecrRepository"],
            image_scan_on_push=True,
        )

        # Apply tags from config
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

from aws_cdk import Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class AwsLegalPocEcrStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.repo = ecr.Repository(
            self,
            "StreamlitRepo",
            repository_name="awslegalpoc-streamlit",
            image_scan_on_push=True,
        )

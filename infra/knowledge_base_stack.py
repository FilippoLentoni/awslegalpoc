from aws_cdk import RemovalPolicy, Stack, Tags
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class AwsLegalPocKnowledgeBaseStack(Stack):
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
        kb_config = config.get("knowledgeBase", {})
        embedding_model = kb_config.get("embeddingModel", "amazon.titan-embed-text-v2:0")
        dimension = kb_config.get("dimension", 1024)
        chunk_max_tokens = kb_config.get("chunkMaxTokens", 512)
        chunk_overlap_percent = kb_config.get("chunkOverlapPercent", 20)

        # 1. S3 data bucket for uploading documents
        data_bucket = s3.Bucket(
            self,
            "KBDataBucket",
            bucket_name=f"{stack_prefix}-kb-data",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
        )

        # 2. S3 Vector bucket
        vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "KBVectorBucket",
            vector_bucket_name=f"{stack_prefix}-kb-vectors",
        )

        # 3. Vector index inside the vector bucket
        vector_index = s3vectors.CfnIndex(
            self,
            "KBVectorIndex",
            vector_bucket_name=f"{stack_prefix}-kb-vectors",
            index_name=f"{stack_prefix}-kb-index",
            dimension=dimension,
            distance_metric="cosine",
            data_type="float32",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=[
                    "AMAZON_BEDROCK_TEXT",
                    "AMAZON_BEDROCK_METADATA",
                ],
            ),
        )
        vector_index.add_dependency(vector_bucket)

        # 4. IAM role for Bedrock Knowledge Base
        kb_role = iam.Role(
            self,
            "KBExecutionRole",
            role_name=f"{stack_prefix}-kb-role",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )

        # Allow invoking the embedding model
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    f"arn:aws:bedrock:{Stack.of(self).region}::foundation-model/{embedding_model}",
                ],
            )
        )

        # Allow reading documents from the data bucket
        data_bucket.grant_read(kb_role)

        # Allow S3 Vectors operations
        kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3vectors:CreateIndex",
                    "s3vectors:GetIndex",
                    "s3vectors:PutVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:DeleteVectors",
                    "s3vectors:ListVectors",
                ],
                resources=[
                    vector_bucket.attr_vector_bucket_arn,
                    f"{vector_bucket.attr_vector_bucket_arn}/*",
                ],
            )
        )

        # 5. Bedrock Knowledge Base
        kb = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"{stack_prefix}-kb",
            role_arn=kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=f"arn:aws:bedrock:{Stack.of(self).region}::foundation-model/{embedding_model}",
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
                    index_arn=vector_index.attr_index_arn,
                ),
            ),
        )
        kb.add_dependency(vector_index)
        kb.node.add_dependency(kb_role)

        # 6. Data Source pointing to the S3 data bucket
        data_source = bedrock.CfnDataSource(
            self,
            "KBDataSource",
            knowledge_base_id=kb.attr_knowledge_base_id,
            name=f"{stack_prefix}-kb-datasource",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=data_bucket.bucket_arn,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=chunk_max_tokens,
                        overlap_percentage=chunk_overlap_percent,
                    ),
                ),
            ),
        )

        # 7. SSM parameters for runtime to read
        ssm.StringParameter(
            self,
            "KBIdParam",
            parameter_name=f"/{stack_prefix}/kb/knowledge-base-id",
            string_value=kb.attr_knowledge_base_id,
        )

        ssm.StringParameter(
            self,
            "KBDataSourceIdParam",
            parameter_name=f"/{stack_prefix}/kb/data-source-id",
            string_value=data_source.attr_data_source_id,
        )

        ssm.StringParameter(
            self,
            "KBDataBucketParam",
            parameter_name=f"/{stack_prefix}/kb/data-bucket-name",
            string_value=data_bucket.bucket_name,
        )

        # Expose for other stacks
        self.knowledge_base_id = kb.attr_knowledge_base_id
        self.data_bucket_name = data_bucket.bucket_name

        # Apply tags
        for key, value in config.get("tags", {}).items():
            Tags.of(self).add(key, value)

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load .env if present (local dev only)
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

AWS_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
BEDROCK_REGION = os.getenv("BEDROCK_REGION") or AWS_REGION
BEDROCK_INFERENCE_PROFILE_ARN = os.getenv("BEDROCK_INFERENCE_PROFILE_ARN")
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID", "amazon.nova-2-lite-v1:0"
)
BEDROCK_KB_ID = os.getenv("KNOWLEDGE_BASE_ID") or os.getenv("BEDROCK_KB_ID")
KB_DATA_BUCKET_NAME = os.getenv("KB_DATA_BUCKET_NAME")
KB_DATA_SOURCE_ID = os.getenv("KB_DATA_SOURCE_ID")

LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

MEMORY_ID = os.getenv("MEMORY_ID")

AGENTCORE_ENABLED = os.getenv("AGENTCORE_ENABLED", "true").lower() == "true"
AGENTCORE_RUNTIME_ARN = os.getenv("AGENTCORE_RUNTIME_ARN")

COGNITO_ENABLED = os.getenv("COGNITO_ENABLED", "true").lower() == "true"
COGNITO_USERNAME = os.getenv("COGNITO_USERNAME")
COGNITO_PASSWORD = os.getenv("COGNITO_PASSWORD")
COGNITO_CONFIG_SECRET = os.getenv("COGNITO_CONFIG_SECRET", "awslegalpoc/cognito-config")

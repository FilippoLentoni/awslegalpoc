import os
import sys
import boto3

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from strands.telemetry import StrandsTelemetry
from opentelemetry import trace as otel_trace

# Ensure core is importable whether it's next to this file or in parent directory
HERE = os.path.dirname(__file__)
candidate_roots = [
    HERE,
    os.path.abspath(os.path.join(HERE, "..")),
]
for root in candidate_roots:
    if os.path.isdir(os.path.join(root, "core")):
        if root not in sys.path:
            sys.path.append(root)
        break

from core.config import BEDROCK_INFERENCE_PROFILE_ARN, BEDROCK_MODEL_ID, BEDROCK_REGION
from core.langfuse_client import get_system_prompt
from core.tools import (
    get_product_info,
    get_return_policy,
    get_technical_support,
    web_search,
)

RUNTIME_REGION = os.getenv("AWS_REGION") or boto3.session.Session().region_name
MODEL_REGION = BEDROCK_REGION or RUNTIME_REGION
MODEL_ID = BEDROCK_INFERENCE_PROFILE_ARN or BEDROCK_MODEL_ID

ssm = boto3.client("ssm", region_name=RUNTIME_REGION)

gateway_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=RUNTIME_REGION,
)

app = BedrockAgentCoreApp()

# Initialize Strands telemetry for Langfuse observability
strands_telemetry = StrandsTelemetry()
strands_telemetry.setup_otlp_exporter()


def _get_ssm_parameter(name: str) -> str:
    return ssm.get_parameter(Name=name, WithDecryption=False)["Parameter"]["Value"]


def _get_gateway_url() -> str:
    try:
        return _get_ssm_parameter("/app/customersupport/agentcore/gateway_url")
    except Exception:
        pass

    gateway_id = _get_ssm_parameter("/app/customersupport/agentcore/gateway_id")
    gateway_response = gateway_client.get_gateway(gatewayIdentifier=gateway_id)
    return gateway_response["gatewayUrl"]


@app.entrypoint
async def invoke(payload, context=None):
    user_input = payload.get("prompt", "")
    actor_id = payload.get("actor_id", "customer_001")
    session_id = context.session_id if context else None

    request_headers = (context.request_headers if context else None) or {}
    auth_header = request_headers.get("Authorization", "")

    if not auth_header:
        return "Error: Missing Authorization header"

    gateway_url = _get_gateway_url()
    if not gateway_url:
        return "Error: Missing AgentCore Gateway URL"

    memory_id = os.environ.get("MEMORY_ID")
    if not memory_id:
        return "Error: MEMORY_ID env var is required"

    # Set Langfuse metadata on the current OTEL span so the trace
    # can be queried by session_id and user_id in the Langfuse dashboard
    current_span = otel_trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attribute("langfuse.session.id", str(session_id))
        current_span.set_attribute("langfuse.user.id", actor_id)

    model = BedrockModel(
        model_id=MODEL_ID,
        temperature=0.3,
        region_name=MODEL_REGION,
    )

    mcp_client = MCPClient(
        lambda: streamablehttp_client(
            url=gateway_url, headers={"Authorization": auth_header}
        )
    )

    with mcp_client:
        tools = [
            get_product_info,
            get_return_policy,
            get_technical_support,
            web_search,
        ] + mcp_client.list_tools_sync()

        memory_config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            session_id=str(session_id),
            actor_id=actor_id,
            retrieval_config={
                "support/customer/{actorId}/semantic/": RetrievalConfig(
                    top_k=3, relevance_score=0.2
                ),
                "support/customer/{actorId}/preferences/": RetrievalConfig(
                    top_k=3, relevance_score=0.2
                ),
            },
        )

        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=get_system_prompt(),
            session_manager=AgentCoreMemorySessionManager(memory_config, RUNTIME_REGION),
        )

        response = agent(user_input)
        return response.message["content"][0]["text"]


if __name__ == "__main__":
    app.run()

import uuid

from strands import Agent
from strands.models import BedrockModel

from bedrock_agentcore.memory.integrations.strands.config import (
    AgentCoreMemoryConfig,
    RetrievalConfig,
)
from bedrock_agentcore.memory.integrations.strands.session_manager import (
    AgentCoreMemorySessionManager,
)

from core.config import (
    BEDROCK_INFERENCE_PROFILE_ARN,
    BEDROCK_MODEL_ID,
    BEDROCK_REGION,
    MEMORY_ID,
)
from core.observability import configure_langfuse_otel
from core.tools import (
    SYSTEM_PROMPT,
    get_product_info,
    get_return_policy,
    get_technical_support,
    web_search,
)


def create_agent(session_id: str, actor_id: str):
    # Configure Langfuse OTEL if available
    configure_langfuse_otel()

    model_id = BEDROCK_INFERENCE_PROFILE_ARN or BEDROCK_MODEL_ID

    model = BedrockModel(
        model_id=model_id,
        temperature=0.3,
        region_name=BEDROCK_REGION,
    )

    tools = [
        get_product_info,
        get_return_policy,
        web_search,
        get_technical_support,
    ]

    if MEMORY_ID:
        memory_config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
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
        session_manager = AgentCoreMemorySessionManager(memory_config, BEDROCK_REGION)
    else:
        session_manager = None

    return Agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        session_manager=session_manager,
    )


def run_agent(prompt: str, session_id: str | None = None, actor_id: str | None = None) -> str:
    session_id = session_id or str(uuid.uuid4())
    actor_id = actor_id or "customer_001"
    agent = create_agent(session_id=session_id, actor_id=actor_id)
    response = agent(prompt)
    return response.message["content"][0]["text"]

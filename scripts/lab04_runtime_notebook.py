# Auto-extracted from lab-04-agentcore-runtime.ipynb
# Each cell preserved verbatim below.

# ---- Cell 1 ----
# Import required libraries
import boto3
from lab_helpers.utils import get_ssm_parameter
from bedrock_agentcore_starter_toolkit.operations.memory.manager import MemoryManager
from bedrock_agentcore.memory.constants import StrategyType
from lab_helpers.lab2_memory import ACTOR_ID

boto_session = boto3.Session()
REGION = boto_session.region_name


memory_name = "CustomerSupportMemory"
memory_manager = MemoryManager(region_name=REGION)
memory = memory_manager.get_or_create_memory( # Just in case the memory lab wasn't executed
    name=memory_name,
    strategies=[
                {
                    StrategyType.USER_PREFERENCE.value: {
                        "name": "CustomerPreferences",
                        "description": "Captures customer preferences and behavior",
                        "namespaces": ["support/customer/{actorId}/preferences/"],
                    }
                },
                {
                    StrategyType.SEMANTIC.value: {
                        "name": "CustomerSupportSemantic",
                        "description": "Stores facts from conversations",
                        "namespaces": ["support/customer/{actorId}/semantic/"],
                    }
                },
            ]
)
memory_id = memory["id"]

# ---- Cell 2 ----
%%writefile ./lab_helpers/lab4_runtime.py
import os
from bedrock_agentcore.runtime import (
    BedrockAgentCoreApp,
)  #### AGENTCORE RUNTIME - LINE 1 ####
from strands import Agent
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
import requests
import boto3
from strands.models import BedrockModel
from lab_helpers.utils import get_ssm_parameter
from lab_helpers.lab1_strands_agent import (
    get_return_policy,
    get_product_info,
    get_technical_support,
    SYSTEM_PROMPT,
    MODEL_ID,
)

from lab_helpers.lab2_memory import (
    ACTOR_ID,
    SESSION_ID,
)
from bedrock_agentcore_starter_toolkit.operations.memory.manager import MemoryManager
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

# Initialize boto3 client
sts_client = boto3.client('sts')

# Get AWS account details
REGION = boto3.session.Session().region_name

# Lab1 import: Create the Bedrock model
model = BedrockModel(model_id=MODEL_ID)

# Lab2 import: Memory
memory_id = os.environ.get("MEMORY_ID")
if not memory_id:
    raise Exception("Environment variable MEMORY_ID is required")

# Initialize the AgentCore Runtime App
app = BedrockAgentCoreApp()  #### AGENTCORE RUNTIME - LINE 2 ####

@app.entrypoint  #### AGENTCORE RUNTIME - LINE 3 ####
async def invoke(payload, context=None):
    """AgentCore Runtime entrypoint function"""
    user_input = payload.get("prompt", "")
    session_id = context.session_id # Get session_id from context
    actor_id = payload.get("actor_id", ACTOR_ID) 
    # Access request headers - handle None case
    request_headers = context.request_headers or {}

    # Get Client JWT token
    auth_header = request_headers.get('Authorization', '')

    print(f"Authorization header: {auth_header}")
    # Get Gateway ID
    existing_gateway_id = get_ssm_parameter("/app/customersupport/agentcore/gateway_id")
    
    # Initialize Bedrock AgentCore Control client
    gateway_client = boto3.client(
        "bedrock-agentcore-control",
        region_name=REGION,
    )
    # Get existing gateway details
    gateway_response = gateway_client.get_gateway(gatewayIdentifier=existing_gateway_id)

    # Get gateway url
    gateway_url = gateway_response['gatewayUrl']

    # Create MCP client and agent within context manager if JWT token available
    if gateway_url and auth_header:
        try:
                mcp_client = MCPClient(lambda: streamablehttp_client(
                    url=gateway_url,
                    headers={"Authorization": auth_header}  
                ))
                
                with mcp_client:
                    tools = (
                        [
                            get_product_info,
                            get_return_policy,
                            get_technical_support
                        ]
                        + mcp_client.list_tools_sync()
                    )

                    memory_config = AgentCoreMemoryConfig(
                        memory_id=memory_id,
                        session_id=str(session_id),
                        actor_id=actor_id,
                        retrieval_config={
                            "support/customer/{actorId}/semantic/": RetrievalConfig(top_k=3, relevance_score=0.2),
                            "support/customer/{actorId}/preferences/": RetrievalConfig(top_k=3, relevance_score=0.2)
                        }
                    )

                    # Create the agent with all customer support tools
                    agent = Agent(
                        model=model,
                        tools=tools,
                        system_prompt=SYSTEM_PROMPT,
                        session_manager=AgentCoreMemorySessionManager(memory_config, REGION),
                    )
                    # Invoke the agent
                    response = agent(user_input)
                    return response.message["content"][0]["text"]
        except Exception as e:
                print(f"MCP client error: {str(e)}")
                return f"Error: {str(e)}"
    else:
        return "Error: Missing gateway URL or authorization header"

if __name__ == "__main__":
    app.run()  #### AGENTCORE RUNTIME - LINE 4 ####

# ---- Cell 3 ----
from lab_helpers.utils import get_or_create_cognito_pool

access_token = get_or_create_cognito_pool(refresh_token=True)
print(f"Access token: {access_token['bearer_token']}")

# ---- Cell 4 ----
from bedrock_agentcore_starter_toolkit import Runtime
from lab_helpers.utils import create_agentcore_runtime_execution_role

# Initialize the runtime toolkit
boto_session = boto3.session.Session()
region = boto_session.region_name

execution_role_arn = create_agentcore_runtime_execution_role()

agentcore_runtime = Runtime()

# Configure the deployment
response = agentcore_runtime.configure(
    entrypoint="lab_helpers/lab4_runtime.py",
    execution_role=execution_role_arn,
    auto_create_ecr=True,
    requirements_file="requirements.txt",
    region=region,
    agent_name="customer_support_agent",
    authorizer_configuration={
        "customJWTAuthorizer": {
            "allowedClients": [
                get_ssm_parameter("/app/customersupport/agentcore/client_id")
            ],
            "discoveryUrl": get_ssm_parameter(
                "/app/customersupport/agentcore/cognito_discovery_url"
            ),
        }
    },
    # Add custom header allowlist for Authorization and custom headers
    request_header_configuration={
        "requestHeaderAllowlist": [
            "Authorization",  # Required for OAuth propogation
            "X-Amzn-Bedrock-AgentCore-Runtime-Custom-H1",  # Custom header
        ]
    },
)

print("Configuration completed:", response)

# ---- Cell 5 ----
# Launch the agent (this will build and deploy the container)
from lab_helpers.utils import put_ssm_parameter

launch_result = agentcore_runtime.launch(env_vars={"MEMORY_ID": memory_id})
print("Launch completed:", launch_result.agent_arn)

agent_arn = put_ssm_parameter(
    "/app/customersupport/agentcore/runtime_arn", launch_result.agent_arn
)

# ---- Cell 6 ----
import time

# Wait for the agent to be ready
status_response = agentcore_runtime.status()
status = status_response.endpoint["status"]

end_status = ["READY", "CREATE_FAILED", "DELETE_FAILED", "UPDATE_FAILED"]
while status not in end_status:
    print(f"Waiting for deployment... Current status: {status}")
    time.sleep(10)
    status_response = agentcore_runtime.status()
    status = status_response.endpoint["status"]

print(f"Final status: {status}")

# ---- Cell 7 ----
# Initialize the AgentCore Control client
client = boto3.client("bedrock-agentcore-control")

# Extract runtime ID from the ARN (format: arn:aws:bedrock-agentcore:region:account:runtime/runtime-id)
runtime_id = launch_result.agent_arn.split(":")[-1].split("/")[-1]

print(f"Runtime ID: {runtime_id}")

# ---- Cell 8 ----
import uuid
from IPython.display import display, Markdown

# Create a session ID for demonstrating session continuity
session_id = uuid.uuid4()

# Test different customer support scenarios
user_query = "List all of your tools"

response = agentcore_runtime.invoke(
    {"prompt": user_query, "actor_id": ACTOR_ID},
    bearer_token=access_token["bearer_token"],
    session_id=str(session_id),
)

display(Markdown(response["response"].replace('\\n', '\n')))

# ---- Cell 9 ----
user_query = "Tell me detailed information about the technical documentation on installing a new CPU"
response = agentcore_runtime.invoke(
    {"prompt": user_query, "actor_id": ACTOR_ID},
    bearer_token=access_token["bearer_token"],
    session_id=str(session_id),
)
display(Markdown(response["response"].replace('\\n', '\n')))

# ---- Cell 10 ----
# Creating a new session ID for demonstrating new customer
session_id2 = uuid.uuid4()

user_query = "I have a Gaming Console Pro device , I want to check my warranty status, warranty serial number is MNO33333333."
response = agentcore_runtime.invoke(
    {"prompt": user_query, "actor_id": ACTOR_ID}, 
    bearer_token=access_token["bearer_token"],
    session_id=str(session_id2),
)
display(Markdown(response["response"].replace('\\n', '\n')))


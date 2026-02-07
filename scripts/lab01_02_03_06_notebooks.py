# Auto-extracted from AgentCore E2E notebooks
# Each section preserves code cells verbatim, including any Jupyter magics.

# 1 notebook code
# ---- Cell 1 ----
# Note: Uncomment and run only for self-paced labs
# !aws sts get-caller-identity 

# ---- Cell 2 ----
# Note: Uncomment and run only for self-paced labs
# !bash scripts/prereq.sh

# ---- Cell 3 ----
# Install required packages 
%pip install -U -r requirements.txt -q

# ---- Cell 4 ----
# Import libraries
import boto3
from boto3.session import Session

from ddgs.exceptions import DDGSException, RatelimitException
from ddgs import DDGS

from strands.tools import tool

# ---- Cell 5 ----
# Get boto session
boto_session = Session()
region = boto_session.region_name

# ---- Cell 6 ----
@tool
def get_return_policy(product_category: str) -> str:
    """
    Get return policy information for a specific product category.

    Args:
        product_category: Electronics category (e.g., 'smartphones', 'laptops', 'accessories')

    Returns:
        Formatted return policy details including timeframes and conditions
    """
    # Mock return policy database - in real implementation, this would query policy database
    return_policies = {
        "smartphones": {
            "window": "30 days",
            "condition": "Original packaging, no physical damage, factory reset required",
            "process": "Online RMA portal or technical support",
            "refund_time": "5-7 business days after inspection",
            "shipping": "Free return shipping, prepaid label provided",
            "warranty": "1-year manufacturer warranty included",
        },
        "laptops": {
            "window": "30 days",
            "condition": "Original packaging, all accessories, no software modifications",
            "process": "Technical support verification required before return",
            "refund_time": "7-10 business days after inspection",
            "shipping": "Free return shipping with original packaging",
            "warranty": "1-year manufacturer warranty, extended options available",
        },
        "accessories": {
            "window": "30 days",
            "condition": "Unopened packaging preferred, all components included",
            "process": "Online return portal",
            "refund_time": "3-5 business days after receipt",
            "shipping": "Customer pays return shipping under $50",
            "warranty": "90-day manufacturer warranty",
        },
    }

    # Default policy for unlisted categories
    default_policy = {
        "window": "30 days",
        "condition": "Original condition with all included components",
        "process": "Contact technical support",
        "refund_time": "5-7 business days after inspection",
        "shipping": "Return shipping policies vary",
        "warranty": "Standard manufacturer warranty applies",
    }

    policy = return_policies.get(product_category.lower(), default_policy)
    return (
        f"Return Policy - {product_category.title()}:\n\n"
        f"• Return window: {policy['window']} from delivery\n"
        f"• Condition: {policy['condition']}\n"
        f"• Process: {policy['process']}\n"
        f"• Refund timeline: {policy['refund_time']}\n"
        f"• Shipping: {policy['shipping']}\n"
        f"• Warranty: {policy['warranty']}"
    )


print("✅ Return policy tool ready")

# ---- Cell 7 ----
@tool
def get_product_info(product_type: str) -> str:
    """
    Get detailed technical specifications and information for electronics products.

    Args:
        product_type: Electronics product type (e.g., 'laptops', 'smartphones', 'headphones', 'monitors')
    Returns:
        Formatted product information including warranty, features, and policies
    """
    # Mock product catalog - in real implementation, this would query a product database
    products = {
        "laptops": {
            "warranty": "1-year manufacturer warranty + optional extended coverage",
            "specs": "Intel/AMD processors, 8-32GB RAM, SSD storage, various display sizes",
            "features": "Backlit keyboards, USB-C/Thunderbolt, Wi-Fi 6, Bluetooth 5.0",
            "compatibility": "Windows 11, macOS, Linux support varies by model",
            "support": "Technical support and driver updates included",
        },
        "smartphones": {
            "warranty": "1-year manufacturer warranty",
            "specs": "5G/4G connectivity, 128GB-1TB storage, multiple camera systems",
            "features": "Wireless charging, water resistance, biometric security",
            "compatibility": "iOS/Android, carrier unlocked options available",
            "support": "Software updates and technical support included",
        },
        "headphones": {
            "warranty": "1-year manufacturer warranty",
            "specs": "Wired/wireless options, noise cancellation, 20Hz-20kHz frequency",
            "features": "Active noise cancellation, touch controls, voice assistant",
            "compatibility": "Bluetooth 5.0+, 3.5mm jack, USB-C charging",
            "support": "Firmware updates via companion app",
        },
        "monitors": {
            "warranty": "3-year manufacturer warranty",
            "specs": "4K/1440p/1080p resolutions, IPS/OLED panels, various sizes",
            "features": "HDR support, high refresh rates, adjustable stands",
            "compatibility": "HDMI, DisplayPort, USB-C inputs",
            "support": "Color calibration and technical support",
        },
    }
    product = products.get(product_type.lower())
    if not product:
        return f"Technical specifications for {product_type} not available. Please contact our technical support team for detailed product information and compatibility requirements."

    return (
        f"Technical Information - {product_type.title()}:\n\n"
        f"• Warranty: {product['warranty']}\n"
        f"• Specifications: {product['specs']}\n"
        f"• Key Features: {product['features']}\n"
        f"• Compatibility: {product['compatibility']}\n"
        f"• Support: {product['support']}"
    )


print("✅ get_product_info tool ready")

# ---- Cell 8 ----
@tool
def web_search(keywords: str, region: str = "us-en", max_results: int = 5) -> str:
    """Search the web for updated information.

    Args:
        keywords (str): The search query keywords.
        region (str): The search region: wt-wt, us-en, uk-en, ru-ru, etc..
        max_results (int | None): The maximum number of results to return.
    Returns:
        List of dictionaries with search results.

    """
    try:
        results = DDGS().text(keywords, region=region, max_results=max_results)
        return results if results else "No results found."
    except RatelimitException:
        return "Rate limit reached. Please try again later."
    except DDGSException as e:
        return f"Search error: {e}"
    except Exception as e:
        return f"Search error: {str(e)}"


print("✅ Web search tool ready")

# ---- Cell 9 ----
import os


def download_files():
    # Get account and region
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    region = boto3.Session().region_name
    bucket_name = f"{account_id}-{region}-kb-data-bucket"

    # Create local folder
    os.makedirs("knowledge_base_data", exist_ok=True)

    # Download all files
    s3 = boto3.client("s3")
    objects = s3.list_objects_v2(Bucket=bucket_name)

    for obj in objects["Contents"]:
        file_name = obj["Key"]
        s3.download_file(bucket_name, file_name, f"knowledge_base_data/{file_name}")
        print(f"Downloaded: {file_name}")

    print("All files saved to: knowledge_base_data/")


# Run it
download_files()

# ---- Cell 10 ----
import time

# Get parameters
ssm = boto3.client("ssm")
bedrock = boto3.client("bedrock-agent")
s3 = boto3.client("s3")

account_id = boto3.client("sts").get_caller_identity()["Account"]
region = boto3.Session().region_name

kb_id = ssm.get_parameter(Name=f"/{account_id}-{region}/kb/knowledge-base-id")[
    "Parameter"
]["Value"]
ds_id = ssm.get_parameter(Name=f"/{account_id}-{region}/kb/data-source-id")[
    "Parameter"
]["Value"]

# Get file names from S3 bucket
bucket_name = f"{account_id}-{region}-kb-data-bucket"
s3_objects = s3.list_objects_v2(Bucket=bucket_name)
file_names = [obj["Key"] for obj in s3_objects.get("Contents", [])]

# Start sync job
response = bedrock.start_ingestion_job(
    knowledgeBaseId=kb_id, dataSourceId=ds_id, description="Quick sync"
)

job_id = response["ingestionJob"]["ingestionJobId"]
print("Bedrock knowledge base sync job started, ingesting the data files from s3")

# Monitor until complete
while True:
    job = bedrock.get_ingestion_job(
        knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id
    )["ingestionJob"]

    status = job["status"]

    if status in ["COMPLETE", "FAILED"]:
        break

    time.sleep(10)

# Print final result
if status == "COMPLETE":
    file_count = job.get("statistics", {}).get("numberOfDocumentsScanned", 0)
    files_list = ", ".join(file_names)
    print(
        f"Bedrock knowledge base sync job completed Successfully, ingested {file_count} files"
    )
    print(f"Files ingested: {files_list}")
else:
    print(f"Bedrock knowledge base sync job failed with status: {status}")

# ---- Cell 11 ----
from strands.models import BedrockModel
from strands import Agent
from strands_tools import retrieve


@tool
def get_technical_support(issue_description: str) -> str:
    try:
        # Get KB ID from parameter store
        ssm = boto3.client("ssm")
        account_id = boto3.client("sts").get_caller_identity()["Account"]
        region = boto3.Session().region_name

        kb_id = ssm.get_parameter(Name=f"/{account_id}-{region}/kb/knowledge-base-id")[
            "Parameter"
        ]["Value"]
        print(f"Successfully retrieved KB ID: {kb_id}")

        # Use strands retrieve tool
        tool_use = {
            "toolUseId": "tech_support_query",
            "input": {
                "text": issue_description,
                "knowledgeBaseId": kb_id,
                "region": region,
                "numberOfResults": 3,
                "score": 0.4,
            },
        }

        result = retrieve.retrieve(tool_use)

        if result["status"] == "success":
            return result["content"][0]["text"]
        else:
            return f"Unable to access technical support documentation. Error: {result['content'][0]['text']}"

    except Exception as e:
        print(f"Detailed error in get_technical_support: {str(e)}")
        return f"Unable to access technical support documentation. Error: {str(e)}"


print("✅ Technical support tool ready")

# ---- Cell 12 ----
SYSTEM_PROMPT = """You are a helpful and professional customer support assistant for an electronics e-commerce company.
Your role is to:
- Provide accurate information using the tools available to you
- Support the customer with technical information and product specifications, and maintenance questions
- Be friendly, patient, and understanding with customers
- Always offer additional help after answering questions
- If you can't help with something, direct customers to the appropriate contact

You have access to the following tools:
1. get_return_policy() - For warranty and return policy questions
2. get_product_info() - To get information about a specific product
3. web_search() - To access current technical documentation, or for updated information. 
4. get_technical_support() - For troubleshooting issues, setup guides, maintenance tips, and detailed technical assistance
For any technical problems, setup questions, or maintenance concerns, always use the get_technical_support() tool as it contains our comprehensive technical documentation and step-by-step guides.

Always use the appropriate tool to get accurate, up-to-date information rather than making assumptions about electronic products or specifications."""

# Initialize the Bedrock model (Anthropic Claude 3.7 Sonnet)
model = BedrockModel(
    model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
    temperature=0.3,
    region_name=region,
)

# Create the customer support agent with all tools
agent = Agent(
    model=model,
    tools=[
        get_product_info,  # Tool 1: Simple product information lookup
        get_return_policy,  # Tool 2: Simple return policy lookup
        web_search,  # Tool 3: Access the web for updated information
        get_technical_support,  # Tool 4: Technical support & troubleshooting
    ],
    system_prompt=SYSTEM_PROMPT,
)

print("Customer Support Agent created successfully!")

# ---- Cell 13 ----
response = agent("What's the return policy for my thinkpad X1 Carbon?")

# ---- Cell 14 ----
response = agent("My laptop won't turn on, what should I check?")

# ---- Cell 15 ----
response = agent(
    "I bought an iphone 14 last month. I don't like it because it heats up. How do I solve it?"
)


# 2 notebook code
# ---- Cell 1 ----
import logging
from boto3.session import Session

from bedrock_agentcore_starter_toolkit.operations.memory.manager import MemoryManager
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.constants import StrategyType

from lab_helpers.utils import put_ssm_parameter

boto_session = Session()
REGION = boto_session.region_name

logger = logging.getLogger(__name__)

# ---- Cell 2 ----
memory_name = "CustomerSupportMemory"

memory_manager = MemoryManager(region_name=REGION)
memory = memory_manager.get_or_create_memory(
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
put_ssm_parameter("/app/customersupport/agentcore/memory_id", memory_id)

# ---- Cell 3 ----
if memory_id:
    print("✅ AgentCore Memory created successfully!")
    print(f"Memory ID: {memory_id}")
else:
    print("Memory resource not created. Try Again !")

# ---- Cell 4 ----
from lab_helpers.lab2_memory import ACTOR_ID


# Seed with previous customer interactions
previous_interactions = [
    ("I'm having issues with my MacBook Pro overheating during video editing.", "USER"),
    (
        "I can help with that thermal issue. For video editing workloads, let's check your Activity Monitor and adjust performance settings. Your MacBook Pro order #MB-78432 is still under warranty.",
        "ASSISTANT",
    ),
    (
        "What's the return policy on gaming headphones? I need low latency for competitive FPS games",
        "USER",
    ),
    (
        "For gaming headphones, you have 30 days to return. Since you're into competitive FPS, I'd recommend checking the audio latency specs - most gaming models have <40ms latency.",
        "ASSISTANT",
    ),
    (
        "I need a laptop under $1200 for programming. Prefer 16GB RAM minimum and good Linux compatibility. I like ThinkPad models.",
        "USER",
    ),
    (
        "Perfect! For development work, I'd suggest looking at our ThinkPad E series or Dell XPS models. Both have excellent Linux support and 16GB RAM options within your budget.",
        "ASSISTANT",
    ),
]

# Save previous interactions
if memory_id:
    try:
        memory_client = MemoryClient(region_name=REGION)
        memory_client.create_event(
            memory_id=memory_id,
            actor_id=ACTOR_ID,
            session_id="previous_session",
            messages=previous_interactions,
        )
        print("✅ Seeded customer history successfully")
        print("📝 Interactions saved to Short-Term Memory")
        print("⏳ Long-Term Memory processing will begin automatically...")
    except Exception as e:
        print(f"⚠️ Error seeding history: {e}")

# ---- Cell 5 ----
import time

# Wait for Long-Term Memory processing to complete
print("🔍 Checking for processed Long-Term Memories...")
retries = 0
max_retries = 6  # 1 minute wait

while retries < max_retries:
    memories = memory_client.retrieve_memories(
        memory_id=memory_id,
        namespace=f"support/customer/{ACTOR_ID}/preferences/",
        query="can you summarize the support issue",
    )

    if memories:
        print(
            f"✅ Found {len(memories)} preference memories after {retries * 10} seconds!"
        )
        break

    retries += 1
    if retries < max_retries:
        print(
            f"⏳ Still processing... waiting 10 more seconds (attempt {retries}/{max_retries})"
        )
        time.sleep(10)
    else:
        print(
            "⚠️ Memory processing is taking longer than expected. This can happen with overloading.."
        )
        break

print(
    "🎯 AgentCore Memory automatically extracted these customer preferences from our seeded conversations:"
)
print("=" * 80)

for i, memory in enumerate(memories, 1):
    if isinstance(memory, dict):
        content = memory.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
            print(f"  {i}. {text}")

# ---- Cell 6 ----
import time

# Retrieve semantic memories (factual information)
while True:
    semantic_memories = memory_client.retrieve_memories(
        memory_id=memory_id,
        namespace=f"support/customer/{ACTOR_ID}/semantic/",
        query="information on the technical support issue",
    )
    print("🧠 AgentCore Memory identified these factual details from conversations:")
    print("=" * 80)
    if semantic_memories:
        break
    time.sleep(10)
for i, memory in enumerate(semantic_memories, 1):
    if isinstance(memory, dict):
        content = memory.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
            print(f"  {i}. {text}")

# ---- Cell 7 ----
import uuid

from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

from lab_helpers.lab1_strands_agent import (
    SYSTEM_PROMPT,
    get_return_policy,
    web_search,
    get_product_info,
    get_technical_support,
    MODEL_ID,
)

session_id = uuid.uuid4()

memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=str(session_id),
        actor_id=ACTOR_ID,
        retrieval_config={
            "support/customer/{actorId}/semantic/": RetrievalConfig(top_k=3, relevance_score=0.2),
            "support/customer/{actorId}/preferences/": RetrievalConfig(top_k=3, relevance_score=0.2)
        }
    )

# Initialize the Bedrock model (Anthropic Claude 3.7 Sonnet)
model = BedrockModel(model_id=MODEL_ID, region_name=REGION)

# Create the customer support agent with all 5 tools
agent = Agent(
    model=model,
    session_manager=AgentCoreMemorySessionManager(memory_config, REGION),
    tools=[
        get_product_info,  # Tool 1: Simple product information lookup
        get_return_policy,  # Tool 2: Simple return policy lookup
        web_search,
        get_technical_support,
    ],
    system_prompt=SYSTEM_PROMPT,
)

# ---- Cell 8 ----
print("🎧 Testing headphone recommendation with customer memory...\n\n")
response1 = agent("Which headphones would you recommend?")

# ---- Cell 9 ----
print("\n💻 Testing laptop preference recall...\n\n")
response2 = agent("What is my preferred laptop brand and requirements?")


# 3 notebook code
# ---- Cell 1 ----
# Import libraries
import os
import sys
import boto3
import json

from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from lab_helpers.utils import (
    get_or_create_cognito_pool,
    put_ssm_parameter,
    get_ssm_parameter,
    load_api_spec,
)


sts_client = boto3.client("sts")
account_id = sts_client.get_caller_identity()['Account']
# Get AWS account details
REGION = boto3.session.Session().region_name

gateway_client = boto3.client(
    "bedrock-agentcore-control",
    region_name=REGION,
)

print("✅ Libraries imported successfully!")

# ---- Cell 2 ----
gateway_name = "customersupport-gw"

cognito_config = get_or_create_cognito_pool(refresh_token=True)
auth_config = {
    "customJWTAuthorizer": {
        "allowedClients": [cognito_config["client_id"]],
        "discoveryUrl": cognito_config["discovery_url"],
    }
}

try:
    # create new gateway
    print(f"Creating gateway in region {REGION} with name: {gateway_name}")

    create_response = gateway_client.create_gateway(
        name=gateway_name,
        roleArn=get_ssm_parameter("/app/customersupport/agentcore/gateway_iam_role"),
        protocolType="MCP",
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration=auth_config,
        description="Customer Support AgentCore Gateway",
    )

    gateway_id = create_response["gatewayId"]

    gateway = {
        "id": gateway_id,
        "name": gateway_name,
        "gateway_url": create_response["gatewayUrl"],
        "gateway_arn": create_response["gatewayArn"],
    }
    put_ssm_parameter("/app/customersupport/agentcore/gateway_id", gateway_id)
    put_ssm_parameter("/app/customersupport/agentcore/gateway_name", gateway_name)
    put_ssm_parameter(
        "/app/customersupport/agentcore/gateway_arn", create_response["gatewayArn"]
    )
    put_ssm_parameter(
        "/app/customersupport/agentcore/gateway_url", create_response["gatewayUrl"]
    )
    print(f"✅ Gateway created successfully with ID: {gateway_id}")

except Exception:
    # If gateway exists, collect existing gateway ID from SSM
    existing_gateway_id = get_ssm_parameter("/app/customersupport/agentcore/gateway_id")
    print(f"Found existing gateway with ID: {existing_gateway_id}")

    # Get existing gateway details
    gateway_response = gateway_client.get_gateway(gatewayIdentifier=existing_gateway_id)
    gateway = {
        "id": existing_gateway_id,
        "name": gateway_response["name"],
        "gateway_url": gateway_response["gatewayUrl"],
        "gateway_arn": gateway_response["gatewayArn"],
    }
    gateway_id = gateway["id"]

# ---- Cell 3 ----
try:
    api_spec_file = "./prerequisite/lambda/api_spec.json"

    # Validate API spec file exists
    if not os.path.exists(api_spec_file):
        print(f"❌ API specification file not found: {api_spec_file}")
        sys.exit(1)

    api_spec = load_api_spec(api_spec_file)

    # Use Cognito for Inbound OAuth to our Gateway
    lambda_target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": get_ssm_parameter(
                    "/app/customersupport/agentcore/lambda_arn"
                ),
                "toolSchema": {"inlinePayload": api_spec},
            }
        }
    }

    # Create gateway target
    credential_config = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

    create_target_response = gateway_client.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name="LambdaUsingSDK",
        description="Lambda Target using SDK",
        targetConfiguration=lambda_target_config,
        credentialProviderConfigurations=credential_config,
    )

    print(f"✅ Gateway target created: {create_target_response['targetId']}")

except Exception as e:
    print(f"❌ Error creating gateway target: {str(e)}")

# ---- Cell 4 ----
print(f"Gateway Endpoint - MCP URL: {gateway['gateway_url']}")
# Set up MCP client
mcp_client = MCPClient(
    lambda: streamablehttp_client(
        gateway["gateway_url"],
        headers={"Authorization": f"Bearer {cognito_config['bearer_token']}"},
    )
)

with mcp_client:
    tools = mcp_client.list_tools_sync()
    print(f"   Found {len(tools)} tool(s):\n")
    for tool in tools:
        print(f"   ✅ {tool.mcp_tool.name}")
        print(f"      {tool.mcp_tool.description}\n")

# ---- Cell 5 ----
from lab_helpers.lab1_strands_agent import (
    get_product_info,
    get_return_policy,
    get_technical_support,
    SYSTEM_PROMPT,
)

import uuid
from lab_helpers.lab2_memory import create_or_get_memory_resource
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

memory_id = create_or_get_memory_resource()

SESSION_ID = str(uuid.uuid4())
CUSTOMER_ID = "customer_001"

memory_config = AgentCoreMemoryConfig(
        memory_id=memory_id,
        session_id=str(SESSION_ID),
        actor_id=CUSTOMER_ID,
        retrieval_config={
            "support/customer/{actorId}/semantic/": RetrievalConfig(top_k=3, relevance_score=0.2),
            "support/customer/{actorId}/preferences/": RetrievalConfig(top_k=3, relevance_score=0.2)
        }
    )

# Initialize the Bedrock model
model_id = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
model = BedrockModel(
    model_id=model_id,
    temperature=0.3,  # Balanced between creativity and consistency
    region_name=REGION,
)


def create_agent(prompt):
    try:
        with mcp_client:
            tools = [
                get_product_info,
                get_return_policy,
                get_technical_support,
            ] + mcp_client.list_tools_sync()

            # Create the customer support agent
            agent = Agent(
                model=model,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
                session_manager=AgentCoreMemorySessionManager(memory_config, REGION),
            )
            response = agent(prompt)
            return response
    except Exception as e:
        raise e


print("✅ Customer support agent created successfully!")

# ---- Cell 6 ----
test_prompts = [
    # Warranty Checks
    "List all of your tools",
    "I bought an iphone 14 last month. I don't like it because it heats up. How do I solve it?",
    "I have a Gaming Console Pro device , I want to check my warranty status, warranty serial number is MNO33333333.",
    "What are the warranty support guidelines?",
    "How can I fix Lenovo Thinkpad with a blue screen",
    "Tell me detailed information about the technical documentation on installing a new CPU",
]


# Function to test the agent
def test_agent_responses(prompts):
    for i, prompt in enumerate(prompts, 1):
        print(f"\nTest Case {i}: {prompt}")
        print("-" * 50)
        try:
            response = create_agent(prompt)
            print(response)
        except Exception as e:
            print(f"Error: {str(e)}")
        print("-" * 50)


# Run the tests
test_agent_responses(test_prompts)

print("\\n✅ Basic testing completed!")

# ---- Cell 7 ----
# Try to import from toolkit, fall back to custom implementation if not available
try:
    from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient
    print("✅ Using toolkit PolicyClient")
except ImportError:
    from utils.policy_utils import PolicyClient
    print("✅ Using custom PolicyClient (toolkit policy module not available)")

# Initialize the policy client
policy_client = PolicyClient(region_name=REGION)

print("\n🔧 Creating Policy Engine...")

# Create or get existing policy engine
# The policy engine is a container for all our authorization policies
engine = policy_client.create_or_get_policy_engine(
    name="customersupport_pe",
    description="Policy engine for customer support gateway",
)

engine_id = engine['policyEngineId']
engine_arn = engine['policyEngineArn']
put_ssm_parameter("/app/customersupport/agentcore/policy_engine_id", engine_id)

print(f"\n✅ Policy Engine ready")
print(f"   Engine ID: {engine_id}")
print(f"   Engine ARN: {engine_arn}")

# ---- Cell 8 ----
import time
# Create Cedar policy for approve tool (write scope)
print("\n📝 Generating Cedar Policy from Natural language...")

nl_input = "Allow tag username == 'testuser' to perform check warranty status on the customer support gateway."

warranty_tool_policy = policy_client.generate_policy(
    policy_engine_id=engine["policyEngineId"],
    name=f"nl_policy_{int(time.time())}",
    resource={"arn": gateway["gateway_arn"]},
    content={"rawText": nl_input},
    fetch_assets=True,
)

print("✅ Policy generated from natural language")

# ---- Cell 9 ----
print("📋 Generated Cedar Policies:\n")
print("=" * 80)

# Allow warranty status policy
print("\n1️⃣  Warranty Status")
print("-" * 80)
warranty_tool_policy_cedar = warranty_tool_policy["generatedPolicies"][0]["definition"]["cedar"]["statement"]
print(warranty_tool_policy_cedar)

print("\n" + "=" * 80)

# ---- Cell 10 ----
# Providing policies to allow for consistency in use case execution
allow_policy = {
    "cedar": {
        "statement": f"""permit(
            principal,
            action in [AgentCore::Action::"LambdaUsingSDK___check_warranty_status", AgentCore::Action::"LambdaUsingSDK___web_search"],
            resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:{REGION}:{account_id}:gateway/{gateway['id']}"
        ) when {{
            (principal.hasTag("username")) && 
            ((principal.getTag("username")) == "testuser")
        }};"""
    }
}

# deny web search for "iPhone 8" keywords
deny_web_search_policy = {
    "cedar": {
        "statement": f"""forbid(
            principal,
            action == AgentCore::Action::"LambdaUsingSDK___web_search",
            resource == AgentCore::Gateway::"arn:aws:bedrock-agentcore:{REGION}:{account_id}:gateway/{gateway['id']}"
        ) when {{
            context.input has keywords &&
            context.input.keywords like "*iPhone 8*"
        }};"""
    }
}

# ---- Cell 11 ----
print("🔧 Creating policies in Policy Engine...\n")

# Create allow both tools policy
warranty_result = policy_client.create_or_get_policy(
    policy_engine_id=engine["policyEngineId"],
    name="allow_policy",
    description="Allow web_search and check_warranty_status calls",
    definition=allow_policy
)
print("✅ Policy ready: allow_policy")
print("   Tools allowed: check_warranty_status and web_search\n")

# Create deny web search list policy
web_search_deny_result = policy_client.create_or_get_policy(
    policy_engine_id=engine["policyEngineId"],
    name="deny_web_search",
    description="Deny web_search tool call for iPhone 8",
    definition=deny_web_search_policy
)
print("✅ Policy ready: deny_web_search")
print("   Tools denied conditionally: web_search\n")

print("✅ All policies ready!")

# ---- Cell 12 ----
role_arn = get_ssm_parameter("/app/customersupport/agentcore/gateway_iam_role")
role_name = role_arn.split('/')[-1] 

iam_client = boto3.client('iam')
print("🔧 Updating Gateway IAM role with Policy Engine permissions...")

# Policy document that grants access to Policy Engine
policy_document = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:*"
            ],
            "Resource": [
                f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:policy-engine/*",
                f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:gateway/*"
            ]
        }
    ]
}

try:
    # Add inline policy to the role
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName="PolicyEngineAccess",
        PolicyDocument=json.dumps(policy_document)
    )
    
    print(f"✅ IAM role updated successfully")
    print(f"   Role: {role_name}")
    print(f"   Added permissions: GetPolicyEngine, GetPolicy, ListPolicies")
    print("\n⏳ Waiting 10 seconds for IAM changes to propagate...")
    time.sleep(10)
    
    print("✅ Ready to attach Policy Engine")
    
except Exception as e:
    print(f"❌ Error updating IAM role: {e}")
    print("\nYou may need to manually add these permissions to the role.")

# ---- Cell 13 ----
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

# Initialize gateway client
gateway_client_toolkit = GatewayClient(region_name=REGION)

print("🔧 Attaching Policy Engine to Gateway...")
print(f"   Mode: ENFORCE (policies will block unauthorized requests)\n")

# Attach the policy engine to the gateway
update_response = gateway_client_toolkit.update_gateway_policy_engine(
    gateway_identifier=gateway["id"],
    policy_engine_arn=engine["policyEngineArn"],
    mode="ENFORCE"
)

print("✅ Policy Engine attached successfully!")
print(f"   Gateway ID: {gateway['id']}")
print(f"   Policy Engine: {engine['policyEngineId']}")
print(f"   Mode: ENFORCE")
print("\n🔒 Authorization is now active!")

# ---- Cell 14 ----
test_prompts = [
    "List all of your tools",
    "Search the web for heating issues with Samsung zfold 7",
    "Search the internet for heating issues with iPhone 8"
]

# Function to test the agent
def test_agent_responses(prompts):
    for i, prompt in enumerate(prompts, 1):
        print(f"\nTest Case {i}: {prompt}")
        print("-" * 50)
        try:
            response = create_agent(prompt)
            print(response)
        except Exception as e:
            print(f"Error: {str(e)}")
        print("-" * 50)

# Run the tests
test_agent_responses(test_prompts)

print("\\n✅ Policy testing completed!")


# 6 notebook code
# ---- Cell 1 ----
# Install frontend-specific dependencies
%pip install -r lab_helpers/lab5_frontend/requirements.txt -q
print("✅ Frontend dependencies installed successfully!")

# ---- Cell 2 ----
# Get the accessible URL for the Streamlit application
from lab_helpers.lab5_frontend.sagemaker_helper import get_streamlit_url

streamlit_url = get_streamlit_url()
print(f"\n🚀 Customer Support Streamlit Application URL:\n{streamlit_url}\n")

# Start the Streamlit application
!cd lab_helpers/lab5_frontend/ && streamlit run main.py



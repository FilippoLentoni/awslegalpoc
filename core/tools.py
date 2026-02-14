import logging
import os

import boto3
from strands.tools import tool

from core.config import BEDROCK_KB_ID, BEDROCK_REGION

logger = logging.getLogger(__name__)

_bedrock_agent_runtime_client = None


def _get_client():
    global _bedrock_agent_runtime_client
    if _bedrock_agent_runtime_client is None:
        region = BEDROCK_REGION or os.getenv("AWS_REGION", "us-east-2")
        _bedrock_agent_runtime_client = boto3.client(
            "bedrock-agent-runtime", region_name=region
        )
    return _bedrock_agent_runtime_client


@tool
def search_knowledge_base(query: str, max_results: int = 5) -> str:
    """Search the knowledge base for relevant information about products,
    return policies, technical support, troubleshooting, and any other
    customer support topics.

    Use this tool whenever the customer asks a question that may be
    answered by our documentation, product information, return policies,
    or technical guides.

    Args:
        query: The search query to find relevant documents
        max_results: Maximum number of results to return (default: 5)

    Returns:
        A formatted string containing the search results with source citations
    """
    knowledge_base_id = os.environ.get("KNOWLEDGE_BASE_ID") or BEDROCK_KB_ID

    if not knowledge_base_id:
        return (
            "Knowledge base search is not available. "
            "The KNOWLEDGE_BASE_ID environment variable is not set."
        )

    client = _get_client()

    try:
        response = client.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": max_results}
            },
        )

        results = response.get("retrievalResults", [])

        if not results:
            return f"No results found for query: {query}"

        formatted_results = []
        for i, result in enumerate(results, 1):
            content = result.get("content", {}).get("text", "No content")
            score = result.get("score", 0)
            location = result.get("location", {})
            source_type = location.get("type", "UNKNOWN")

            if source_type == "S3":
                source = location.get("s3Location", {}).get("uri", "Unknown")
            else:
                source = f"Source type: {source_type}"

            text = f"Result {i} (Relevance: {score:.2f})\n"
            text += f"Source: {source}\n"
            if len(content) > 800:
                content = content[:800] + "..."
            text += f"Content: {content}\n"
            formatted_results.append(text)

        return "\n---\n".join(formatted_results)

    except Exception as e:
        logger.error(f"Error searching knowledge base: {e}")
        return f"Error searching knowledge base: {str(e)}"


SYSTEM_PROMPT = """You are a helpful and professional customer support assistant.

Your role is to:
- Provide accurate information by searching the knowledge base
- Support the customer with product information, return policies, technical support, and troubleshooting
- Be friendly, patient, and understanding with customers
- Always offer additional help after answering questions
- If you can't help with something, direct customers to the appropriate contact

You have access to:
1. search_knowledge_base() - Search our comprehensive documentation for product info, return policies, technical guides, troubleshooting steps, and more.

Always use the search_knowledge_base tool to find accurate, up-to-date information rather than making assumptions. If the knowledge base does not contain relevant results, let the customer know and suggest contacting support directly."""

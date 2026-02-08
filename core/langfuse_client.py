from typing import Optional

from core.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

LANGFUSE_PROMPT_NAME = "customer-support-agent"


def get_langfuse_client():
    if not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        return None

    try:
        from langfuse import Langfuse
    except Exception:
        return None

    try:
        return Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
    except Exception:
        return None


def get_system_prompt() -> str:
    """Fetch system prompt from Langfuse Prompt Management, fall back to hardcoded."""
    from core.tools import SYSTEM_PROMPT

    lf = get_langfuse_client()
    if not lf:
        return SYSTEM_PROMPT

    try:
        prompt = lf.get_prompt(LANGFUSE_PROMPT_NAME, type="text", fallback=SYSTEM_PROMPT)
        return prompt.compile()
    except Exception:
        return SYSTEM_PROMPT

"""Seed the system prompt into Langfuse Prompt Management.

Usage:
    set -a && source .env && set +a && python3.11 scripts/seed_langfuse_prompt.py
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.langfuse_client import get_langfuse_client, LANGFUSE_PROMPT_NAME
from core.tools import SYSTEM_PROMPT

lf = get_langfuse_client()
if not lf:
    print("ERROR: Langfuse client not configured. Check LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY.")
    sys.exit(1)

# Always create a new version (Langfuse auto-increments version numbers)
prompt = lf.create_prompt(
    name=LANGFUSE_PROMPT_NAME,
    prompt=SYSTEM_PROMPT,
    labels=["production"],
)
print(f"Created prompt '{LANGFUSE_PROMPT_NAME}' (version {prompt.version}) with label 'production'.")
print("You can edit it in the Langfuse UI: Prompt Management > customer-support-agent")

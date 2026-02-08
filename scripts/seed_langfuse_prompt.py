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

# Check if prompt already exists
try:
    existing = lf.get_prompt(LANGFUSE_PROMPT_NAME, type="text")
    print(f"Prompt '{LANGFUSE_PROMPT_NAME}' already exists (version {existing.version}). Skipping.")
    print("Edit it in the Langfuse UI: Prompt Management > customer-support-agent")
except Exception:
    # Prompt doesn't exist yet - create it
    prompt = lf.create_prompt(
        name=LANGFUSE_PROMPT_NAME,
        prompt=SYSTEM_PROMPT,
        labels=["production"],
    )
    print(f"Created prompt '{LANGFUSE_PROMPT_NAME}' (version {prompt.version}) with label 'production'.")
    print("You can now edit it in the Langfuse UI: Prompt Management > customer-support-agent")

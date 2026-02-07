from typing import Optional

from core.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY


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

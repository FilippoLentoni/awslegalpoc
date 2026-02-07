import base64
import os

from core.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY


def configure_langfuse_otel() -> bool:
    """Configure OTEL exporter env vars for Langfuse if keys are present.

    Returns True if configuration was applied.
    """
    if not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        return False

    otel_endpoint = LANGFUSE_HOST.rstrip("/") + "/api/public/otel"
    auth_token = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode("utf-8")
    ).decode("utf-8")

    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", otel_endpoint)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_HEADERS", f"Authorization=Basic {auth_token}")
    os.environ.setdefault("DISABLE_ADOT_OBSERVABILITY", "true")
    return True

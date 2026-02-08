import time
import uuid
from datetime import datetime, timedelta, timezone

import streamlit as st

from core.agent import run_agent
from core.agentcore_runtime_client import invoke_agentcore_runtime
from core.cognito_auth import (
    authenticate_user,
    get_or_create_cognito_config,
)
from core.config import (
    AGENTCORE_ENABLED,
    COGNITO_ENABLED,
    COGNITO_PASSWORD,
    COGNITO_USERNAME,
)
from core.langfuse_client import get_langfuse_client


st.set_page_config(page_title="AWS Legal POC")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "actor_id" not in st.session_state:
    st.session_state.actor_id = "customer_001"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_trace_id" not in st.session_state:
    st.session_state.last_trace_id = None
if "last_generation_id" not in st.session_state:
    st.session_state.last_generation_id = None
if "last_prompt" not in st.session_state:
    st.session_state.last_prompt = None
if "last_request_time" not in st.session_state:
    st.session_state.last_request_time = None

st.title("AWS Legal POC - Customer Support Assistant")

# Temporary in-app Cognito authentication (no ALB)
if COGNITO_ENABLED and "auth_token" not in st.session_state:
    st.subheader("Sign in")

    default_user = COGNITO_USERNAME or ""
    default_pass = COGNITO_PASSWORD or ""

    username = st.text_input("Username", value=default_user)
    password = st.text_input("Password", value=default_pass, type="password")

    if st.button("Sign in"):
        if not username or not password:
            st.error("Username and password are required.")
            st.stop()

        try:
            config = get_or_create_cognito_config()
            # Use pre-provisioned user from bootstrap script; avoid AdminCreateUser in ECS
            token = authenticate_user(username, password, config)
            st.session_state.auth_token = token
            st.success("Signed in.")
            st.rerun()
        except Exception as exc:
            st.error(f"Sign in failed: {exc}")
            st.stop()

    st.stop()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


def _find_runtime_trace(prompt: str, request_time: datetime, max_retries: int = 6) -> str:
    """
    Find the AgentCore Runtime OTEL trace that matches the given prompt.

    Queries recent traces and matches by input text. Retries with increasing
    delays since OTEL traces take time to be indexed in Langfuse.
    """
    lf = get_langfuse_client()
    if not lf:
        return None

    # Use a generous time window: 5 minutes before request_time (or None to skip filter)
    from_ts = None
    if request_time:
        from_ts = request_time - timedelta(minutes=5)

    for attempt in range(max_retries):
        try:
            kwargs = {"limit": 10}
            if from_ts:
                kwargs["from_timestamp"] = from_ts

            response = lf.api.trace.list(**kwargs)

            if response and response.data:
                # First try to match by prompt text in trace input
                if prompt:
                    for trace in response.data:
                        trace_input = str(trace.input) if trace.input else ""
                        if prompt in trace_input:
                            return trace.id

                # Fallback: return the most recent trace
                return response.data[0].id

        except Exception as e:
            print(f"[feedback] Error querying traces (attempt {attempt + 1}): {e}", flush=True)

        # Increasing delay: 2, 3, 4, 5, 6, 7 seconds
        if attempt < max_retries - 1:
            time.sleep(2 + attempt)

    return None


def _log_langfuse(prompt: str, response: str):
    """
    Log interaction to Langfuse.

    When AgentCore is enabled, the runtime already creates traces via OTEL,
    so we skip creating duplicate traces here. We just store a marker that
    a trace exists for this session.

    When AgentCore is disabled (local agent mode), we create traces manually.
    """
    lf = get_langfuse_client()
    if not lf:
        return

    if AGENTCORE_ENABLED:
        # Runtime already traced via OTEL - don't create duplicate
        # Mark that we should look up the trace later for feedback
        st.session_state.last_trace_id = "LOOKUP_REQUIRED"
        st.session_state.last_generation_id = None
        return

    # Local agent mode - create trace manually
    try:
        trace = lf.trace(
            name="chat_session",
            session_id=st.session_state.session_id,
            user_id=st.session_state.actor_id,
            input=prompt,
            output=response,
        )
        generation = trace.generation(
            name="agent_response",
            input=prompt,
            output=response,
        )

        st.session_state.last_trace_id = getattr(trace, "id", None)
        st.session_state.last_generation_id = getattr(generation, "id", None)
    except Exception:
        # Non-blocking; chat should still work
        st.session_state.last_trace_id = None
        st.session_state.last_generation_id = None


def _send_feedback(value: int):
    """
    Send user feedback (thumbs up/down) to Langfuse.

    Links the feedback to the correct trace:
    - For AgentCore mode: queries Langfuse to find the runtime trace by session_id
    - For local agent mode: uses the stored trace_id
    """
    lf = get_langfuse_client()
    if not lf:
        return

    # Determine which trace to link the feedback to
    trace_id = None

    if st.session_state.last_trace_id == "LOOKUP_REQUIRED":
        # AgentCore mode - find the runtime trace by prompt + timestamp
        prompt = st.session_state.get("last_prompt")
        req_time = st.session_state.get("last_request_time")
        print(f"[feedback] Looking up trace: prompt={prompt!r}, request_time={req_time}", flush=True)

        with st.spinner("Submitting feedback..."):
            trace_id = _find_runtime_trace(prompt, req_time)

        print(f"[feedback] Found trace_id={trace_id}", flush=True)
        if not trace_id:
            st.warning("Could not link feedback to trace. Please try again.")
            return
    else:
        # Local agent mode - use stored trace_id
        trace_id = st.session_state.last_trace_id

    if not trace_id:
        st.warning("No trace available for feedback.")
        return

    try:
        lf.create_score(
            trace_id=trace_id,
            name="thumbs_feedback",
            value=float(value),
            comment="User feedback from Streamlit UI",
        )
    except Exception as e:
        st.error(f"Failed to submit feedback: {e}")


if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.last_prompt = prompt
    st.session_state.last_request_time = datetime.now(timezone.utc)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            if AGENTCORE_ENABLED:
                try:
                    response_text = invoke_agentcore_runtime(
                        prompt,
                        bearer_token=st.session_state.auth_token,
                        session_id=st.session_state.session_id,
                        actor_id=st.session_state.actor_id,
                    )
                except Exception as exc:
                    st.error(f"AgentCore runtime call failed: {exc}")
                    st.stop()
            else:
                response_text = run_agent(
                    prompt,
                    session_id=st.session_state.session_id,
                    actor_id=st.session_state.actor_id,
                )
        st.markdown(response_text)

    st.session_state.messages.append(
        {"role": "assistant", "content": response_text}
    )
    _log_langfuse(prompt, response_text)

# Thumbs feedback for latest assistant message
if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Helpful", key="thumbs_up"):
            _send_feedback(1)
            st.success("Thanks for the feedback!")
    with col2:
        if st.button("Not helpful", key="thumbs_down"):
            _send_feedback(0)
            st.info("Thanks for the feedback! We'll improve.")

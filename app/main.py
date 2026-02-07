import uuid

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


def _log_langfuse(prompt: str, response: str):
    lf = get_langfuse_client()
    if not lf:
        return

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
    lf = get_langfuse_client()
    if not lf or not st.session_state.last_trace_id:
        return

    try:
        lf.score(
            trace_id=st.session_state.last_trace_id,
            name="thumbs_feedback",
            value=value,
            comment="User feedback from Streamlit UI",
        )
    except Exception:
        pass


if prompt := st.chat_input("Ask a question..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

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

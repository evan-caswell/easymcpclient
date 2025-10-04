import os
import httpx
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

if "history" not in st.session_state:
    st.session_state.history = []

user_input = st.chat_input()

for message in st.session_state.history:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    elif message["role"] == "assistant":
        with st.chat_message("assistant"):
            st.markdown(message["content"])

with httpx.Client(base_url=f"{API_BASE_URL}/chat", timeout=60.0) as client:
    if user_input:
        st.session_state.history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("_thinking..._")

        payload = {
            "prompt": user_input,
            "thread_id": "thread-1" # Unique thread ID should be passed here. More robust implementation is recommended.
        }
        response = client.post(url=f"{API_BASE_URL}/chat", json=payload)
        response.raise_for_status()
        output = response.json()
        reply = output["reply"]

        st.session_state.history.append(
            {"role": "assistant", "content": reply}
        )
        placeholder.markdown(reply)



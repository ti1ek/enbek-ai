"""Streamlit stub UI — local testing, placeholder for production Next.js."""
import streamlit as st
import httpx

st.set_page_config(
    page_title="Enbek AI — Трудовое Право РК",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "http://localhost:8000/api/v1"

if "messages" not in st.session_state:
    st.session_state.messages = []


def ask_api(question: str, pipeline: str) -> dict | None:
    try:
        r = httpx.post(
            f"{API_BASE}/ask",
            json={"question": question, "pipeline": pipeline},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Ошибка запроса: {e}")
        return None


# ---------- Sidebar ----------
with st.sidebar:
    st.title("⚖️ Enbek AI")
    st.caption("AI-ассистент по трудовому праву РК")
    st.divider()
    pipeline = st.radio("Режим RAG:", ["advanced", "basic"], index=0)
    st.caption("Advanced: HyDE + Cohere rerank\nBasic: прямой embedding поиск (для A/B)")

# ---------- Chat ----------
st.header("Вопросы по трудовому праву РК")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Задайте вопрос по трудовому праву РК..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Ищу в нормативных актах..."):
            result = ask_api(prompt, pipeline)
        if result:
            st.markdown(result["answer"])
            st.caption(f"⏱ {result['latency_ms']} мс | {result['pipeline'].upper()} RAG")
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["answer"],
            })

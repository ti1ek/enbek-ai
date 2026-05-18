"""Streamlit stub UI — local testing, placeholder for production Next.js."""
import streamlit as st
import httpx
import json
from datetime import datetime

st.set_page_config(
    page_title="Enbek AI — Трудовое Право РК",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE = "http://localhost:8000/api/v1"

# ---------- Session state ----------
if "token" not in st.session_state:
    st.session_state.token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "queries_today" not in st.session_state:
    st.session_state.queries_today = 0


# ---------- Auth helpers ----------
def login(email: str, password: str) -> bool:
    try:
        from supabase import create_client
        import os
        from dotenv import load_dotenv
        load_dotenv()
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.token = res.session.access_token
        st.session_state.user_email = email
        return True
    except Exception as e:
        st.error(f"Ошибка входа: {e}")
        return False


def register(email: str, password: str) -> bool:
    try:
        from supabase import create_client
        import os
        from dotenv import load_dotenv
        load_dotenv()
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
        sb.auth.sign_up({"email": email, "password": password})
        st.success("Регистрация прошла! Теперь войдите.")
        return True
    except Exception as e:
        st.error(f"Ошибка регистрации: {e}")
        return False


def ask_api(question: str, pipeline: str) -> dict | None:
    try:
        r = httpx.post(
            f"{API_BASE}/ask",
            json={"question": question, "pipeline": pipeline},
            headers={"Authorization": f"Bearer {st.session_state.token}"},
            timeout=60.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            st.warning("Дневной лимит запросов исчерпан.")
        else:
            st.error(f"API error {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Ошибка запроса: {e}")
        return None


# ---------- Login page ----------
def show_login():
    st.title("⚖️ Enbek AI — Трудовое Право РК")
    st.subheader("AI-ассистент для вопросов по трудовому законодательству Казахстана")

    tab_login, tab_register = st.tabs(["Войти", "Зарегистрироваться"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль", type="password")
            if st.form_submit_button("Войти", type="primary", use_container_width=True):
                if login(email, password):
                    st.rerun()

    with tab_register:
        with st.form("register_form"):
            email = st.text_input("Email")
            password = st.text_input("Пароль (min 8 символов)", type="password")
            if st.form_submit_button("Зарегистрироваться", use_container_width=True):
                register(email, password)


# ---------- Main app ----------
def show_app():
    # Sidebar
    with st.sidebar:
        st.markdown(f"**{st.session_state.user_email}**")
        st.metric("Запросов сегодня", st.session_state.queries_today)
        st.divider()
        pipeline = st.radio("Режим RAG:", ["advanced", "basic"], index=0)
        st.caption("Advanced: HyDE + гибридный поиск + Cohere rerank\nBasic: прямой embedding поиск (для A/B)")
        st.divider()
        if st.button("Выйти"):
            st.session_state.token = None
            st.session_state.user_email = None
            st.session_state.messages = []
            st.rerun()

    tab_chat, tab_doc, tab_gen = st.tabs(["💬 Консультация", "📋 Проверить документ", "✍️ Создать договор"])

    # --- Tab 1: Chat ---
    with tab_chat:
        st.header("Вопросы по трудовому праву РК")

        # Display history
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("sources"):
                    with st.expander(f"📚 Источники ({len(msg['sources'])})"):
                        for s in msg["sources"]:
                            label = f"{s.get('source_type', '?')} | ст. {s.get('article', '?')}"
                            if s.get("url"):
                                st.markdown(f"- [{label}]({s['url']})")
                            else:
                                st.markdown(f"- {label}")

        # Input
        if prompt := st.chat_input("Задайте вопрос по трудовому праву РК..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Ищу в нормативных актах..."):
                    result = ask_api(prompt, pipeline)
                if result:
                    st.markdown(result["answer"])
                    if result.get("sources"):
                        with st.expander(f"📚 Источники ({len(result['sources'])})"):
                            for s in result["sources"]:
                                label = f"{s.get('source_type', '?')} | ст. {s.get('article', '?')}"
                                if s.get("url"):
                                    st.markdown(f"- [{label}]({s['url']}) (score: {s.get('score', 0):.3f})")
                                else:
                                    st.markdown(f"- {label}")

                    st.caption(f"⏱ {result['latency_ms']} мс | 💰 ${result['cost_usd']:.5f} | {result['pipeline'].upper()} RAG")
                    st.session_state.queries_today = result.get("queries_used_today", 0)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result["answer"],
                        "sources": result.get("sources", []),
                    })

    # --- Tab 2: Document check ---
    with tab_doc:
        st.header("Проверка трудового документа")
        st.caption("Загрузите трудовой договор, приказ или другой документ — AI проверит соответствие ТК РК")

        uploaded = st.file_uploader(
            "Документ (PDF, DOCX, JPG, PNG)",
            type=["pdf", "docx", "jpg", "jpeg", "png"],
            key="doc_upload",
        )
        if uploaded:
            st.info(f"Файл: {uploaded.name} ({uploaded.size // 1024} KB) — функция активируется в следующем обновлении (этап 2.2)")
            # TODO(day2): call /api/v1/documents/check endpoint

    # --- Tab 3: Document generation ---
    with tab_gen:
        st.header("Создать трудовой договор")
        st.caption("Заполните параметры — AI сгенерирует договор в соответствии с ТК РК")

        with st.form("gen_form"):
            col1, col2 = st.columns(2)
            with col1:
                position = st.text_input("Должность", placeholder="Менеджер по продажам")
                salary = st.number_input("Оклад (тенге)", min_value=0, step=10000)
                probation = st.selectbox("Испытательный срок", ["Без испытания", "1 месяц", "2 месяца", "3 месяца"])
            with col2:
                schedule = st.selectbox("Режим работы", ["5/2 (9:00-18:00)", "Сменный", "Гибкий", "Удалённый"])
                contract_type = st.selectbox("Тип договора", ["Бессрочный", "Срочный (1 год)", "Срочный (2 года)"])
                vacation_days = st.number_input("Отпуск (дней)", min_value=24, max_value=60, value=24)

            if st.form_submit_button("Сгенерировать договор", type="primary", use_container_width=True):
                st.info("Генерация договора активируется в следующем обновлении (этап 2.2)")
                # TODO(day2): call /api/v1/documents/generate endpoint


if __name__ == "__main__" or True:
    if st.session_state.token:
        show_app()
    else:
        show_login()

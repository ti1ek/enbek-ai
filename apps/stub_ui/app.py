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
ATTACH_TYPES = ["png", "jpg", "jpeg", "webp", "pdf", "docx", "txt", "md"]

if "messages" not in st.session_state:
    st.session_state.messages = []


def extract_api(file) -> dict | None:
    """Send an attached file to /extract and return extracted text + metadata."""
    try:
        r = httpx.post(
            f"{API_BASE}/extract",
            files={"file": (file.name, file.getvalue(), file.type or "application/octet-stream")},
            timeout=180.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        st.error(f"Не удалось извлечь {file.name}: {e.response.status_code} {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Ошибка извлечения {file.name}: {e}")
        return None


def ask_api(question: str, pipeline: str, attachment_text: str = "") -> dict | None:
    try:
        r = httpx.post(
            f"{API_BASE}/ask",
            json={"question": question, "pipeline": pipeline, "attachment_text": attachment_text},
            timeout=120.0,
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
    st.divider()
    st.caption("📎 Можно прикрепить документ (фото/скан/PDF/DOCX) — "
               "система извлечёт текст и учтёт его при ответе.")

# ---------- Chat ----------
st.header("Вопросы по трудовому праву РК")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

submission = st.chat_input(
    "Спросите или прикрепите документ…",
    accept_file=True,
    file_type=ATTACH_TYPES,
)

if submission:
    prompt = (submission.text or "").strip()
    files = submission.files or []

    # 1. Extract text from any attachments
    attachment_text = ""
    attach_notes: list[str] = []
    for f in files:
        with st.spinner(f"Извлекаю текст из {f.name}…"):
            ext = extract_api(f)
        if ext and ext.get("text"):
            attachment_text += f"\n\n[{f.name}]\n{ext['text']}"
            note = f"{f.name} ({ext['method']}, {ext['chars']} симв.)"
            if ext.get("truncated"):
                note += " ⚠️ обрезан"
            attach_notes.append(note)
        elif ext:
            attach_notes.append(f"{f.name} — текст не извлечён")

    if not prompt and not attachment_text:
        st.stop()
    if not prompt:
        prompt = "Проанализируй приложенный документ на соответствие трудовому праву РК."

    # 2. Render user turn (with attachment note)
    user_display = prompt
    if attach_notes:
        user_display += "\n\n📎 *Вложения:* " + "; ".join(attach_notes)
    st.session_state.messages.append({"role": "user", "content": user_display})
    with st.chat_message("user"):
        st.markdown(user_display)

    # 3. Ask
    with st.chat_message("assistant"):
        with st.spinner("Ищу в нормативных актах…"):
            result = ask_api(prompt, pipeline, attachment_text.strip())
        if result:
            st.markdown(result["answer"])
            st.caption(f"⏱ {result['latency_ms']} мс | {result['pipeline'].upper()} RAG")
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["answer"],
            })

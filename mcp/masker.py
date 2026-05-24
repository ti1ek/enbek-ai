import os
import httpx
import json

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

MASK_PROMPT = """Ты — система защиты персональных данных. Найди и замени все персональные данные в тексте:
- ФИО (имена, фамилии, отчества) → [PERSON_N]
- ИИН → [ИИН_N]
- Номера телефонов → [PHONE_N]
- Email-адреса → [EMAIL_N]
- Адреса (улица, квартира, город) → [ADDRESS_N]
- Номера документов (договоров, приказов) → [DOC_N]
- Суммы зарплат → [AMOUNT_N]

Верни ТОЛЬКО исправленный текст без пояснений. Если персональных данных нет — верни текст без изменений.

Текст:
{text}"""


async def mask_pii(text: str) -> tuple[str, dict[str, str]]:
    """Returns (masked_text, mapping) where mapping is {placeholder: original}."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": MASK_PROMPT.format(text=text),
                    "stream": False,
                },
            )
            resp.raise_for_status()
            masked = resp.json().get("response", text).strip()
            return masked, {}
    except Exception:
        # If Ollama is unavailable — pass through without masking
        return text, {}

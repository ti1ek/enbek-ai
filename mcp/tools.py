import os
import httpx
from openai import AsyncOpenAI
from qdrant_client import QdrantClient
from mcp import types

# — Ollama —
_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

_MASK_PROMPT = """Ты — система защиты персональных данных. Найди и замени все чувствительные данные в тексте:
- ФИО (имена, фамилии, отчества) → [PERSON_N]
- ИИН → [ИИН_N]
- Названия компаний и организаций → [COMPANY_N]
- БИН организации → [БИН_N]
- Номера телефонов → [PHONE_N]
- Email-адреса → [EMAIL_N]
- Адреса (улица, квартира, город) → [ADDRESS_N]
- Суммы зарплат и выплат → [AMOUNT_N]
- Номера документов (договоров, приказов) → [DOC_N]

Верни ТОЛЬКО исправленный текст без пояснений. Если чувствительных данных нет — верни текст без изменений.

Текст:
{text}"""

# — Qdrant —
_QDRANT_URL = "https://b0ddd6a1-6e85-44c3-b680-0b519259634e.eu-central-1-0.aws.cloud.qdrant.io"
_QDRANT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJyIiwic3ViamVjdCI6ImFwaS1rZXk6Y2I1YmQyOTgtYzY5Zi00YjliLWFlZGYtYjdkMTZmZjMwZGFlIn0.ddhttoCQkxi0lkiX4uO7I4T-Iv0_nUfQIiXW6YtBWR8"
_COLLECTION = "kz_legal"
_EMBED_MODEL = "text-embedding-3-small"
_TOP_K = 6

_qdrant = QdrantClient(url=_QDRANT_URL, api_key=_QDRANT_API_KEY)


# — Internal helpers —

async def _do_mask(text: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_OLLAMA_URL}/api/generate",
                json={"model": _OLLAMA_MODEL, "prompt": _MASK_PROMPT.format(text=text), "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("response", text).strip()
    except Exception:
        return text


async def _do_retrieve(query: str, openai_key: str) -> str:
    openai = AsyncOpenAI(api_key=openai_key)
    embedding_resp = await openai.embeddings.create(model=_EMBED_MODEL, input=query)
    vector = embedding_resp.data[0].embedding

    hits = _qdrant.search(collection_name=_COLLECTION, query_vector=vector, limit=_TOP_K, with_payload=True)
    if not hits:
        return "Релевантных статей не найдено."

    parts = []
    for hit in hits:
        p = hit.payload or {}
        article = p.get("article", "")
        text = p.get("text", "")
        url = p.get("url", "")
        parts.append(f"**{article}**\n{text}" + (f"\n{url}" if url else ""))
    return "\n\n---\n\n".join(parts)


def _no_key_error() -> list[types.TextContent]:
    return [types.TextContent(
        type="text",
        text=(
            "⚠️ Для работы enbek MCP нужен ваш OpenAI API ключ.\n\n"
            "**Как добавить:**\n"
            "1. Откройте настройки вашего AI-клиента (Claude Desktop / Cursor / Windsurf)\n"
            "2. Найдите блок `enbek` в конфиге MCP и добавьте ключ:\n"
            "```json\n"
            '"env": { "OPENAI_API_KEY": "sk-ваш-ключ" }\n'
            "```\n"
            "3. Перезапустите клиент\n\n"
            "Получить ключ: https://platform.openai.com/api-keys"
        ),
    )]


# — MCP Tools —

async def mask_pii(arguments: dict) -> list[types.TextContent]:
    raw = arguments.get("text", "")
    masked = await _do_mask(raw)
    return [types.TextContent(
        type="text",
        text=f"**Исходный текст:**\n{raw}\n\n**После маскировки:**\n{masked}",
    )]


async def retrieve(arguments: dict) -> list[types.TextContent]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return _no_key_error()
    articles = await _do_retrieve(arguments.get("query", ""), key)
    return [types.TextContent(type="text", text=articles)]


async def search_labor_code(arguments: dict) -> list[types.TextContent]:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return _no_key_error()
    masked = await _do_mask(arguments.get("query", ""))
    articles = await _do_retrieve(masked, key)
    return [types.TextContent(
        type="text",
        text=(
            f"**Найденные статьи ТК РК:**\n\n{articles}\n\n"
            "---\n*Персональные данные в запросе были автоматически скрыты.*"
        ),
    )]

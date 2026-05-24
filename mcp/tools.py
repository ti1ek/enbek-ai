import os
from mcp import types
from lib.masker import mask_pii as _mask_pii
from lib.retriever import search as _search


def _openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")


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


async def mask_pii(arguments: dict) -> list[types.TextContent]:
    """Маскирует персональные данные в тексте локально через Ollama."""
    raw = arguments.get("text", "")
    masked, _ = await _mask_pii(raw)
    return [types.TextContent(
        type="text",
        text=f"**Исходный текст:**\n{raw}\n\n**После маскировки:**\n{masked}",
    )]


async def retrieve(arguments: dict) -> list[types.TextContent]:
    """Возвращает сырые чанки из Qdrant без дополнительной обработки."""
    key = _openai_key()
    if not key:
        return _no_key_error()

    query = arguments.get("query", "")
    articles = await _search(query, key)
    return [types.TextContent(type="text", text=articles)]


async def search_labor_code(arguments: dict) -> list[types.TextContent]:
    """Полный пайплайн: маскировка персональных данных → поиск по ТК РК."""
    key = _openai_key()
    if not key:
        return _no_key_error()

    raw = arguments.get("query", "")
    masked, _ = await _mask_pii(raw)
    articles = await _search(masked, key)
    return [types.TextContent(
        type="text",
        text=(
            f"**Найденные статьи ТК РК:**\n\n{articles}\n\n"
            "---\n*Персональные данные в запросе были автоматически скрыты.*"
        ),
    )]

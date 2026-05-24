import os
from mcp import types
from masker import mask_pii
from retriever import search


async def search_labor_code(arguments: dict) -> list[types.TextContent]:
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
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

    raw = arguments.get("query", "")
    masked, _ = await mask_pii(raw)
    articles = await search(masked, openai_key)

    return [types.TextContent(
        type="text",
        text=(
            f"**Найденные статьи ТК РК:**\n\n{articles}\n\n"
            "---\n*Персональные данные в запросе были автоматически скрыты.*"
        ),
    )]

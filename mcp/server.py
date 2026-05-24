import asyncio
import os
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from masker import mask_pii
from retriever import search

load_dotenv()

app = Server("enbek")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_labor_code",
            description=(
                "Поиск по Трудовому кодексу Республики Казахстан. "
                "Автоматически скрывает персональные данные (ФИО, ИИН) перед отправкой запроса. "
                "Возвращает релевантные статьи с цитатами и ссылками."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Вопрос или описание ситуации на русском языке",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="analyze_document",
            description=(
                "Анализ трудового документа (договор, приказ, уведомление) "
                "на соответствие Трудовому кодексу РК. "
                "Персональные данные маскируются локально до отправки в поиск."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "document_text": {
                        "type": "string",
                        "description": "Текст документа целиком или фрагмент",
                    }
                },
                "required": ["document_text"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        return [types.TextContent(
            type="text",
            text="Ошибка: не задан OPENAI_API_KEY. Добавьте его в настройках MCP.",
        )]

    if name == "search_labor_code":
        raw = arguments.get("query", "")
        masked, _ = await mask_pii(raw)
        articles = await search(masked, openai_key)
        result = (
            f"**Найденные статьи ТК РК:**\n\n{articles}\n\n"
            "---\n*Персональные данные в запросе были автоматически скрыты.*"
        )
        return [types.TextContent(type="text", text=result)]

    if name == "analyze_document":
        raw = arguments.get("document_text", "")
        masked, _ = await mask_pii(raw)
        articles = await search(
            f"Анализ документа: {masked[:500]}", openai_key
        )
        result = (
            f"**Релевантные статьи ТК РК для анализа:**\n\n{articles}\n\n"
            "---\n*Персональные данные в документе были автоматически скрыты перед поиском.*"
        )
        return [types.TextContent(type="text", text=result)]

    return [types.TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

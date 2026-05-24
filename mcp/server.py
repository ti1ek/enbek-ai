import asyncio
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from tools import search_labor_code

load_dotenv()

app = Server("enbek")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_labor_code",
            description=(
                "Поиск по Трудовому кодексу Республики Казахстан. "
                "Автоматически скрывает персональные данные (ФИО, ИИН, названия компаний) "
                "перед отправкой запроса. Возвращает релевантные статьи с цитатами и ссылками."
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
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "search_labor_code":
        return await search_labor_code(arguments)
    return [types.TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

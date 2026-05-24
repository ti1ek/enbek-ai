import asyncio
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from tools import mask_pii, retrieve, search_labor_code

load_dotenv()

app = Server("enbek")


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="mask_pii",
            description=(
                "Маскирует персональные данные в тексте локально на компьютере пользователя. "
                "ФИО, ИИН, названия компаний, БИН, телефоны, адреса и суммы заменяются "
                "на безопасные метки. Данные не покидают компьютер."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Текст с персональными данными для маскировки",
                    }
                },
                "required": ["text"],
            },
        ),
        types.Tool(
            name="retrieve",
            description=(
                "Поиск сырых чанков по Трудовому кодексу РК в векторной базе Qdrant. "
                "Возвращает релевантные фрагменты без дополнительной обработки."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос на русском языке",
                    }
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="search_labor_code",
            description=(
                "Полный пайплайн: маскировка персональных данных → поиск по ТК РК. "
                "Используй этот инструмент когда в вопросе могут быть персональные данные."
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
    if name == "mask_pii":
        return await mask_pii(arguments)
    if name == "retrieve":
        return await retrieve(arguments)
    if name == "search_labor_code":
        return await search_labor_code(arguments)
    return [types.TextContent(type="text", text=f"Неизвестный инструмент: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

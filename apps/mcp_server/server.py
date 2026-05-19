"""MCP server for Enbek AI — local PII protection layer.

Tool:
  mask_pii — mask PII before sending to cloud LLM

Run: python apps/mcp_server/server.py
Connect via MCP Inspector or Claude Desktop.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server.fastmcp import FastMCP
from apps.mcp_server.tools.mask_pii import mask_pii as _mask_pii

mcp = FastMCP(
    "enbek-pii-guard",
    instructions=(
        "Локальный сервис защиты персональных данных для Enbek AI. "
        "Используется HR-специалистами и юристами перед отправкой документов в облачные LLM. "
        "Маскирует ИИН, ФИО, телефоны, email, IBAN."
    ),
)


@mcp.tool(
    description=(
        "Маскирует персональные данные (ПДн) в тексте перед отправкой в облачный LLM. "
        "Заменяет: ИИН (с валидацией контрольной суммы РК), ФИО (3-словные паттерны), "
        "телефоны (+7/8 7XX), email-адреса, IBAN (KZ...). "
        "Возвращает замаскированный текст и mapping для последующего восстановления. "
        "ВАЖНО: сохраните mapping — без него восстановить данные невозможно."
    )
)
def mask_pii(text: str) -> dict:
    """Mask PII in a document before sending to cloud LLM.

    Args:
        text: Raw document or message text containing potential PII.

    Returns:
        masked_text: Text with PII replaced by placeholders like [PERSON_1], [IIN_1].
        mapping: Dict mapping placeholders back to original values.
        stats: Count of each PII type found.
    """
    return _mask_pii(text)


if __name__ == "__main__":
    mcp.run(transport="stdio")

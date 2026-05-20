"""MCP server for Enbek AI — local PII protection layer.

Tools:
  mask_pii        — mask PII before sending to cloud LLM
  validate_kz_iin — validate Kazakhstan IIN and extract metadata

Run: python apps/mcp_server/server.py
Connect via MCP Inspector or Claude Desktop.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server.fastmcp import FastMCP
from apps.mcp_server.tools.mask_pii import mask_pii as _mask_pii
from apps.mcp_server.tools.validate_kz_iin import validate_kz_iin as _validate_kz_iin

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


@mcp.tool(
    description=(
        "Проверяет ИИН (Индивидуальный Идентификационный Номер) физического лица РК. "
        "Валидирует контрольную сумму по алгоритму МЮ РК, извлекает дату рождения, "
        "пол и век рождения. Полезно перед отправкой ИИН в государственные системы "
        "или при проверке кадровых документов сотрудников."
    )
)
def validate_kz_iin(iin: str) -> dict:
    """Validate a Kazakhstan IIN and extract encoded metadata.

    Args:
        iin: 12-digit IIN string (spaces are stripped automatically).

    Returns:
        valid: True if IIN passes checksum validation.
        iin: Cleaned IIN string.
        errors: List of validation error messages (empty if valid).
        dob: Date of birth in DD.MM.YYYY format, or null.
        gender: "M" or "F", or null.
        century: Birth century range e.g. "1900-1999", or null.
    """
    return _validate_kz_iin(iin)


if __name__ == "__main__":
    mcp.run(transport="stdio")

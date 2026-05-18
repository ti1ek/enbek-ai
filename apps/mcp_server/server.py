"""MCP server for Enbek AI — local PII protection layer.

Tools:
  1. mask_pii            — mask PII before sending to cloud LLM
  2. unmask_pii_response — restore PII in LLM response
  3. validate_kz_iin     — validate KZ IIN and extract metadata

Run: python apps/mcp_server/server.py
Connect via MCP Inspector or Claude Desktop.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server.fastmcp import FastMCP
from apps.mcp_server.tools.mask_pii import mask_pii as _mask_pii
from apps.mcp_server.tools.validate_kz_iin import validate_kz_iin as _validate_iin

mcp = FastMCP(
    "enbek-pii-guard",
    instructions=(
        "Локальный сервис защиты персональных данных для Enbek AI. "
        "Используется HR-специалистами и юристами перед отправкой документов в облачные LLM. "
        "Маскирует ИИН, ФИО, телефоны, email, IBAN. "
        "После получения ответа LLM — восстанавливает данные через unmask_pii_response."
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
        "Восстанавливает персональные данные в ответе LLM. "
        "Принимает текст с placeholder'ами ([PERSON_1], [IIN_1] и т.д.) и mapping "
        "из предыдущего вызова mask_pii. Подставляет реальные данные обратно. "
        "Используется ПОСЛЕ получения ответа от облачного LLM."
    )
)
def unmask_pii_response(masked_text: str, mapping: dict) -> dict:
    """Restore PII in LLM response using the mapping from mask_pii.

    Args:
        masked_text: LLM response containing [PERSON_1], [IIN_1] etc. placeholders.
        mapping: The mapping dict returned by mask_pii (placeholder → original).

    Returns:
        restored_text: Text with placeholders replaced back by real values.
        replacements_made: Number of successful replacements.
    """
    result = masked_text
    count = 0
    for placeholder, original in mapping.items():
        if placeholder in result:
            result = result.replace(placeholder, original)
            count += 1
    return {
        "restored_text": result,
        "replacements_made": count,
    }


@mcp.tool(
    description=(
        "Валидирует ИИН (Индивидуальный Идентификационный Номер) по алгоритму "
        "контрольной суммы Министерства юстиции РК. "
        "Извлекает: дату рождения, пол, век. "
        "Полезен при проверке трудовых договоров и кадровых документов. "
        "Не требует отправки данных в облако — работает локально."
    )
)
def validate_kz_iin(iin: str) -> dict:
    """Validate a Kazakhstan IIN (Individual Identification Number).

    Args:
        iin: 12-digit IIN string to validate.

    Returns:
        valid: Whether the IIN passes checksum validation.
        iin: The input IIN.
        errors: List of validation errors (empty if valid).
        dob: Date of birth extracted from IIN (DD.MM.YYYY) or None.
        gender: "M" or "F" or None.
        century: Birth century range e.g. "1900-1999".
    """
    return _validate_iin(iin)


if __name__ == "__main__":
    mcp.run(transport="stdio")

"""MCP server for Enbek AI — labor law Q&A with local PII protection.

Tools:
  ask_labor_law — answer labor law questions via Advanced RAG; masks PII locally
  mask_pii      — mask PII in any text before sending to cloud LLM

Run: uv run python apps/mcp_server/server.py
Connect via Claude Desktop or MCP Inspector.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from mcp.server.fastmcp import FastMCP
from apps.mcp_server.tools.ask_labor_law import ask_labor_law as _ask_labor_law
from apps.mcp_server.tools.mask_pii import mask_pii as _mask_pii

mcp = FastMCP(
    "enbek-ai",
    instructions=(
        "Система ИИ-консультирования по трудовому праву Казахстана (ТК РК, Социальный кодекс, "
        "приказы Минтруда, НП ВС РК). "
        "Все персональные данные (ИИН, ФИО, телефоны, IBAN) маскируются локально "
        "до отправки в облачный LLM. "
        "Используется HR-специалистами и юристами для проверки кадровых решений."
    ),
)


@mcp.tool(
    description=(
        "Отвечает на вопросы по трудовому праву РК с цитатами и ссылками на нормативные акты. "
        "Использует Advanced RAG по корпусу: ТК РК, Социальный кодекс, КоАП, приказы Минтруда, "
        "НП ВС РК. "
        "Если передать document_text (трудовой договор, приказ, заявление сотрудника), "
        "ПДн (ИИН, ФИО, телефоны, IBAN) будут автоматически замаскированы локально "
        "до отправки в LLM — персональные данные не покидают вашу машину."
    )
)
def ask_labor_law(question: str, document_text: str = "") -> dict:
    """Ask a labor law question with optional employee document.

    Args:
        question: Question in Russian or Kazakh about labor law, dismissal,
                  leave, salary, disciplinary action, etc.
        document_text: Optional text of an employee document (contract, order,
                       complaint) that may contain PII — masked automatically.

    Returns:
        answer: Detailed legal answer with citations (article numbers, links).
        sources: List of referenced legal acts with URLs where available.
        pii_masked: Count of masked PII by type (e.g. {"IIN": 1, "NAME": 2}).
        latency_ms: Response time in milliseconds.
    """
    return _ask_labor_law(question, document_text)


@mcp.tool(
    description=(
        "Маскирует персональные данные (ПДн) в тексте перед отправкой в облачный LLM. "
        "Заменяет: ИИН (с валидацией контрольной суммы РК), ФИО (3-словные паттерны), "
        "телефоны (+7/8 7XX), email-адреса, IBAN (KZ...). "
        "Возвращает замаскированный текст и mapping для восстановления. "
        "Используй этот инструмент отдельно если нужно передать текст в другой сервис."
    )
)
def mask_pii(text: str) -> dict:
    """Mask PII in a document before sending to any cloud LLM.

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

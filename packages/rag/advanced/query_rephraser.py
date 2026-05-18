"""HyDE + query expansion for KZ labor law questions."""
import json
from openai import OpenAI
from packages.config import settings

_llm: OpenAI | None = None


def _get_llm() -> OpenAI:
    global _llm
    if _llm is None:
        _llm = OpenAI(api_key=settings.openai_api_key)
    return _llm


def rephrase_query(question: str) -> dict:
    """Return expanded query dict with hypothetical answer (HyDE) and synonyms.

    Returns:
        {
            "canonical": str,     # cleaned question
            "hyde": str,          # hypothetical answer for embedding
            "synonyms": list[str] # alternative phrasings
        }
    """
    prompt = f"""Ты — эксперт по трудовому законодательству Казахстана.

Вопрос пользователя: "{question}"

Выполни три задачи и верни JSON:
1. "canonical" — перефразируй вопрос в юридически точную форму (на русском)
2. "hyde" — напиши гипотетический короткий ответ (2-4 предложения) со ссылками на статьи ТК РК, \
как будто ты уже знаешь ответ. Это используется для семантического поиска.
3. "synonyms" — дай 2-3 альтернативные формулировки того же вопроса

Верни ТОЛЬКО JSON без пояснений:
{{"canonical": "...", "hyde": "...", "synonyms": ["...", "..."]}}"""

    llm = _get_llm()
    response = llm.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=400,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return {
        "canonical": data.get("canonical", question),
        "hyde": data.get("hyde", question),
        "synonyms": data.get("synonyms", []),
    }

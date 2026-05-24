"""HyDE + query expansion + decomposition for KZ labor law questions."""
import json
from packages.config import settings
from packages.llm import chat_complete
from packages.rag.prompts import DECOMPOSE_PROMPT_RU


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

    response = chat_complete(
        model=settings.llm_mini_model,
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


def decompose_question(question: str, max_subs: int = 4) -> list[str]:
    """Split a complex question into 1-4 entity-focused sub-questions.

    Returns a non-empty list. On failure or for simple questions falls back to [question].
    """
    if len(question.split()) < 6:
        return [question]

    try:
        response = chat_complete(
            model=settings.llm_mini_model,
            messages=[{"role": "user", "content": DECOMPOSE_PROMPT_RU.format(question=question)}],
            temperature=0.0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        subs = data.get("sub_questions") or []
    except Exception:
        return [question]

    if not isinstance(subs, list):
        return [question]
    cleaned: list[str] = []
    seen: set[str] = set()
    for s in subs:
        if not isinstance(s, str):
            continue
        s = s.strip()
        if len(s.split()) < 5:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)
        if len(cleaned) >= max_subs:
            break
    return cleaned or [question]

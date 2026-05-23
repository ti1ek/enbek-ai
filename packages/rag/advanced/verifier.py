"""Self-RAG verifier: critique a draft RAG answer and propose a retry retrieval query.

Used by the LangGraph `verifier_node` (after the synthesizer, before citation_guard).
Behind the ENABLE_VERIFIER flag. When disabled, the graph short-circuits past this module.
"""
import json

from packages.config import settings
from packages.llm import chat_complete
from packages.rag.prompts import VERIFIER_PROMPT_RU


def _format_cited(sources: list[dict]) -> str:
    if not sources:
        return "(нет процитированных источников)"
    parts: list[str] = []
    for s in sources[:8]:
        st = s.get("source_type") or s.get("label") or "?"
        art = str(s.get("article") or "").strip()
        para = str(s.get("paragraph") or "").strip()
        doc_name = s.get("doc_name") or ""
        bits = [st]
        if art:
            bits.append(f"ст.{art}")
        if para and not para.startswith("block"):
            bits.append(f"п.{para}")
        if doc_name and doc_name not in " ".join(bits):
            bits.append(doc_name)
        parts.append(" ".join(bits))
    return "; ".join(parts)


def critique_draft(question: str, draft: str, sources: list[dict], context: str) -> dict:
    """Return critique of a draft answer.

    Returns:
        {
          "is_valid": bool,
          "critique": str,
          "missing_norms": list[str],
          "retry_query": str,
        }

    On any LLM/parsing failure returns is_valid=True (fail-open: don't loop forever).
    """
    cited = _format_cited(sources)
    context_excerpt = (context or "")[:2500]
    draft_short = (draft or "")[:1800]

    prompt = VERIFIER_PROMPT_RU.format(
        question=question,
        cited=cited,
        context_excerpt=context_excerpt,
        draft=draft_short,
    )
    try:
        response = chat_complete(
            model=settings.llm_mini_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception:
        return {"is_valid": True, "critique": "", "missing_norms": [], "retry_query": ""}

    is_valid = bool(data.get("is_valid", True))
    retry_query = (data.get("retry_query") or "").strip()
    missing = data.get("missing_norms") or []
    if isinstance(missing, str):
        missing = [missing]
    missing = [str(m).strip() for m in missing if str(m).strip()]

    # If LLM said invalid but gave no retry query — synthesize one from missing_norms
    if not is_valid and not retry_query and missing:
        retry_query = " ".join(missing[:3])

    # If LLM said invalid but supplied neither critique nor retry_query — treat as fail-open
    if not is_valid and not retry_query and not missing:
        is_valid = True

    return {
        "is_valid": is_valid,
        "critique": (data.get("critique") or "").strip(),
        "missing_norms": missing,
        "retry_query": retry_query,
    }

"""Baseline RAG pipeline — used for A/B comparison."""
import time
from openai import OpenAI
from langsmith import traceable
from packages.config import settings
from packages.rag.embeddings import embed_query
from packages.rag.qdrant_client import dense_search
from packages.rag.prompts import SYSTEM_LEGAL_RU, RAG_PROMPT_TEMPLATE

_llm: OpenAI | None = None


def _get_llm() -> OpenAI:
    global _llm
    if _llm is None:
        _llm = OpenAI(api_key=settings.openai_api_key)
    return _llm


@traceable(name="basic_rag")
def basic_rag(question: str, top_k: int = 5) -> dict:
    t0 = time.perf_counter()

    # 1. Embed query
    q_vector = embed_query(question)

    # 2. Dense retrieval
    hits = dense_search(query_vector=q_vector, top_k=top_k, in_force_only=True)

    # 3. Build context
    context_parts = []
    sources = []
    for hit in hits:
        p = hit.payload or {}
        context_parts.append(
            f"[{p.get('source_type', '')} | {p.get('article', '')} п.{p.get('paragraph', '')}]\n{p.get('text', '')}"
        )
        sources.append({
            "source_type": p.get("source_type"),
            "article": p.get("article"),
            "paragraph": p.get("paragraph"),
            "url": p.get("url"),
        })

    context = "\n\n---\n\n".join(context_parts) if context_parts else "Контекст не найден."
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    # 4. Generate
    llm = _get_llm()
    response = llm.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_LEGAL_RU},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=1500,
    )
    answer = response.choices[0].message.content or ""
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Rough cost: input + output tokens at gpt-4.1 prices ($2.50/$10 per 1M)
    usage = response.usage
    cost_usd = ((usage.prompt_tokens * 2.50) + (usage.completion_tokens * 10.0)) / 1_000_000

    return {
        "answer": answer,
        "sources": sources,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "pipeline": "basic",
    }

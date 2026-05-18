"""Advanced RAG pipeline: HyDE + hybrid search + Cohere rerank."""
import time
from openai import OpenAI
from langsmith import traceable
from packages.config import settings
from packages.rag.embeddings import embed_query, embed_texts
from packages.rag.qdrant_client import dense_search, hybrid_search
from packages.rag.advanced.query_rephraser import rephrase_query
from packages.rag.retrieval.reranker import rerank
from packages.rag.prompts import SYSTEM_LEGAL_RU, RAG_PROMPT_TEMPLATE

_llm: OpenAI | None = None


def _get_llm() -> OpenAI:
    global _llm
    if _llm is None:
        _llm = OpenAI(api_key=settings.openai_api_key)
    return _llm


@traceable(name="advanced_rag")
def advanced_rag(question: str, top_k_retrieve: int = 15, top_n_rerank: int = 5) -> dict:
    t0 = time.perf_counter()
    total_prompt_tokens = 0
    total_completion_tokens = 0

    # 1. Query rephrasing: canonical + HyDE + synonyms (gpt-4.1-mini)
    rephrased = rephrase_query(question)
    canonical = rephrased["canonical"]
    hyde_text = rephrased["hyde"]

    # 2. Embed: original + HyDE (average for richer representation)
    orig_vector = embed_query(question)
    hyde_vector = embed_query(hyde_text)
    # Average the two embeddings
    avg_vector = [(a + b) / 2 for a, b in zip(orig_vector, hyde_vector)]

    # 3. Dense retrieval with averaged vector
    hits = dense_search(query_vector=avg_vector, top_k=top_k_retrieve, in_force_only=True)

    if not hits:
        # Fallback to original vector
        hits = dense_search(query_vector=orig_vector, top_k=top_k_retrieve, in_force_only=False)

    # 4. Cohere rerank
    docs = [{"text": h.payload.get("text", ""), **h.payload} for h in hits if h.payload]
    reranked_docs = rerank(query=canonical or question, documents=docs, top_n=top_n_rerank)

    # If Cohere failed (no results), fall back to dense order
    if not reranked_docs:
        reranked_docs = [{"text": h.payload.get("text", ""), **h.payload, "rerank_score": h.score}
                         for h in hits[:top_n_rerank] if h.payload]

    # 5. Build context using parent_text when available
    context_parts = []
    sources = []
    for doc in reranked_docs:
        ctx_text = doc.get("parent_text") or doc.get("text", "")
        context_parts.append(
            f"[{doc.get('source_type', '')} | ст.{doc.get('article', '')} п.{doc.get('paragraph', '')}]\n{ctx_text}"
        )
        sources.append({
            "source_type": doc.get("source_type"),
            "article": doc.get("article"),
            "paragraph": doc.get("paragraph"),
            "url": doc.get("url"),
            "score": doc.get("rerank_score", 0.0),
        })

    context = "\n\n---\n\n".join(context_parts) if context_parts else "Контекст не найден."
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    # 6. Synthesize with GPT-4.1
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
    usage = response.usage
    total_prompt_tokens += usage.prompt_tokens
    total_completion_tokens += usage.completion_tokens

    latency_ms = int((time.perf_counter() - t0) * 1000)
    cost_usd = ((total_prompt_tokens * 2.50) + (total_completion_tokens * 10.0)) / 1_000_000

    return {
        "answer": answer,
        "sources": sources,
        "latency_ms": latency_ms,
        "cost_usd": cost_usd,
        "pipeline": "advanced",
        "rephrased": rephrased,
    }

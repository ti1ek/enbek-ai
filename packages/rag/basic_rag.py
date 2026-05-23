"""Baseline RAG pipeline — used for A/B comparison."""
import re
import time
from langsmith import traceable
from packages.config import settings
from packages.llm import chat_complete
from packages.rag.embeddings import embed_query
from packages.rag.qdrant_client import dense_search
from packages.rag.prompts import SYSTEM_LEGAL_RU, RAG_PROMPT_TEMPLATE, build_attachment_block


@traceable(name="basic_rag")
def basic_rag(question: str, top_k: int = 5, attachment_text: str = "") -> dict:
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
        st = p.get("source_type", "")
        art = p.get("article", "")
        para = p.get("paragraph", "")
        url = p.get("url") if not p.get("inactive_count", 0) else None

        url_hint = ""
        if url:
            text_preview = p.get("text", "")
            if st == "labor_code":
                link_text = f"ст. {art} ТК РК" if art and art != "0" else "ТК РК"
            elif st == "social_code":
                link_text = f"ст. {art} Социального кодекса РК" if art and art != "0" else "Социального кодекса РК"
            elif st == "koap":
                link_text = f"ст. {art} КоАП РК" if art and art != "0" else "КоАП РК"
            elif st in {"ministerial_order", "government_decree"}:
                doc_name = p.get("doc_name", "Приказа")
                m = re.match(r"^(\d+)[.\)]", text_preview.strip())
                para_num = m.group(1) if m else ""
                link_text = f"п. {para_num} {doc_name}" if para_num else doc_name
            elif st in {"mintrud_dialog", "mintrud_faq"}:
                link_text = "Разъяснение Минтруда РК"
            else:
                link_text = st
            url_hint = f"\n→ Ссылка: [{link_text}]({url})"

        context_parts.append(
            f"[{st} | ст.{art} п.{para}]{url_hint}\n{p.get('text', '')}"
        )
        sources.append({
            "source_type": st,
            "article": art,
            "paragraph": para,
            "url": url,
            "text": p.get("text", ""),
        })

    context = "\n\n---\n\n".join(context_parts) if context_parts else "Контекст не найден."
    attachment_block = build_attachment_block(attachment_text)
    if attachment_block:
        context = attachment_block + "\n\n---\n\n" + context
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    # 4. Generate
    response = chat_complete(
        model=settings.llm_model,
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

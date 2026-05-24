"""Core RAG tool for Enbek AI MCP — labor law Q&A."""
import os
from typing import Any


def ask_labor_law(question: str, document_text: str = "") -> dict[str, Any]:
    """Answer a labor law question using Advanced RAG over КЗ legal corpus.

    If document_text is provided, it should already be masked via mask_pii tool.

    Args:
        question: User question in Russian or Kazakh.
        document_text: Optional document text (pre-masked via mask_pii if contains PII).

    Returns:
        answer: Legal answer with citations.
        sources: List of source chunks with article, url, source_type.
        pipeline: Pipeline label.
        latency_ms: Response time in milliseconds.
    """
    # Production-optimal flags from ablation study (faithfulness 0.703)
    os.environ.setdefault("ENABLE_HYDE", "false")
    os.environ.setdefault("ENABLE_RERANK", "false")

    from apps.api.graph import run_graph
    result = run_graph(question, pipeline="advanced", attachment_text=document_text)

    formatted_sources = []
    for s in result.get("sources", []):
        art = s.get("article", "")
        st = s.get("source_type", "")
        url = s.get("url")
        label = f"ст. {art} ({st})" if art and art != "0" else st
        entry = {"label": label, "source_type": st, "article": art}
        if url:
            entry["url"] = url
        formatted_sources.append(entry)

    return {
        "answer": result.get("answer", ""),
        "sources": formatted_sources,
        "pipeline": "advanced",
        "latency_ms": result.get("latency_ms", 0),
    }

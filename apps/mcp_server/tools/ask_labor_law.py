"""Core RAG tool for Enbek AI MCP — labor law Q&A with PII protection."""
import os
from typing import Any

from apps.mcp_server.tools.mask_pii import mask_pii


def ask_labor_law(question: str, document_text: str = "") -> dict[str, Any]:
    """Answer a labor law question using Advanced RAG over КЗ legal corpus.

    If document_text is provided, PII (IIN, names, phones, IBAN) is masked
    locally before any data is sent to the cloud LLM.

    Args:
        question: User question in Russian or Kazakh.
        document_text: Optional employee document or case text containing PII.

    Returns:
        answer: Legal answer with citations.
        sources: List of source chunks with article, url, source_type.
        pii_masked: Count of each PII type masked (empty if no document).
        pipeline: Pipeline label ("advanced").
        latency_ms: Response time in milliseconds.
    """
    # 1. Mask PII from document before it touches any cloud API
    masked_doc = ""
    pii_stats: dict[str, int] = {}
    if document_text.strip():
        pii_result = mask_pii(document_text)
        masked_doc = pii_result["masked_text"]
        pii_stats = {k: v for k, v in pii_result["stats"].items() if v > 0}

    # 2. Production-optimal flags from ablation study (faithfulness 0.703)
    os.environ.setdefault("ENABLE_HYDE", "false")
    os.environ.setdefault("ENABLE_RERANK", "false")

    # 3. Run Advanced RAG
    from apps.api.graph import run_graph
    result = run_graph(question, pipeline="advanced", attachment_text=masked_doc)

    # 4. Format sources for display
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
        "pii_masked": pii_stats,
        "pipeline": "advanced",
        "latency_ms": result.get("latency_ms", 0),
    }

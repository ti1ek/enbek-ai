import time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from apps.api.auth import get_current_user
from apps.api.db import log_query, queries_today

router = APIRouter()

class AskRequest(BaseModel):
    question: str
    pipeline: str = "advanced"  # basic | advanced
    doc_text: str = ""           # optional: document text for doc_* pipelines


class Source(BaseModel):
    source_type: str | None = None   # labor_code, mintrud_dialog, etc.
    doc_name: str | None = None      # human-readable document name
    article: str | None = None       # article number, e.g. "96"
    paragraph: str | None = None
    url: str | None = None           # source document URL (adilet / egov / gov.kz / tkrk.kz)


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    classification: str | None = None  # qa / doc_generate / appeal_court / etc.
    latency_ms: int
    cost_usd: float
    pipeline: str
    queries_used_today: int


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, user: dict = Depends(get_current_user)):
    used = queries_today(user["id"])
    daily_limit = user.get("daily_limit", 10)
    if used >= daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Дневной лимит {daily_limit} запросов исчерпан.",
        )

    t0 = time.perf_counter()

    question = req.question
    doc_text = req.doc_text

    if req.pipeline == "basic":
        from packages.rag.basic_rag import basic_rag
        result = basic_rag(question)
    else:
        # Use LangGraph for all other pipelines (advanced, doc_*)
        from apps.api.graph import run_graph
        graph_result = run_graph(
            question=question,
            pipeline=req.pipeline,
            doc_text=doc_text,
        )
        result = {
            "answer": graph_result["answer"],
            "sources": graph_result["sources"],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "cost_usd": 0.0,  # tracked inside graph nodes
            "pipeline": req.pipeline,
        }

    result.setdefault("latency_ms", int((time.perf_counter() - t0) * 1000))
    result.setdefault("cost_usd", 0.0)

    await log_query(
        user_id=user["id"],
        query_text=question,  # masked for МСП users, original for others
        response_text=result["answer"],
        sources=result["sources"],
        pipeline=result["pipeline"],
        latency_ms=result["latency_ms"],
        cost_usd=result["cost_usd"],
    )

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        classification=result.get("classification"),
        latency_ms=result["latency_ms"],
        cost_usd=result["cost_usd"],
        pipeline=result["pipeline"],
        queries_used_today=used + 1,
    )

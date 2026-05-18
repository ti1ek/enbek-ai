import time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from apps.api.auth import get_current_user
from apps.api.db import log_query, queries_today
from packages.config import settings
from packages.rag.basic_rag import basic_rag

router = APIRouter()

DAILY_LIMIT = 50  # per user per day (free tier)


class AskRequest(BaseModel):
    question: str
    pipeline: str = "basic"  # basic | advanced


class AskResponse(BaseModel):
    answer: str
    sources: list[dict]
    latency_ms: int
    cost_usd: float
    pipeline: str
    queries_used_today: int


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, user: dict = Depends(get_current_user)):
    # Rate limit check
    used = queries_today(user["id"])
    if used >= DAILY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Дневной лимит {DAILY_LIMIT} запросов исчерпан.",
        )

    # Run pipeline
    if req.pipeline == "advanced":
        # Imported lazily to avoid circular deps at startup
        try:
            from packages.rag.advanced_rag import advanced_rag
            result = advanced_rag(req.question)
        except ImportError:
            result = basic_rag(req.question)
    else:
        result = basic_rag(req.question)

    # Log
    await log_query(
        user_id=user["id"],
        query_text=req.question,
        response_text=result["answer"],
        sources=result["sources"],
        pipeline=result["pipeline"],
        latency_ms=result["latency_ms"],
        cost_usd=result["cost_usd"],
    )

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        latency_ms=result["latency_ms"],
        cost_usd=result["cost_usd"],
        pipeline=result["pipeline"],
        queries_used_today=used + 1,
    )

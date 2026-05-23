import time
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class AskRequest(BaseModel):
    question: str
    pipeline: str = "advanced"  # basic | advanced


class Source(BaseModel):
    source_type: str | None = None
    doc_name: str | None = None
    article: str | None = None
    paragraph: str | None = None
    url: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    classification: str | None = None
    latency_ms: int
    cost_usd: float
    pipeline: str


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    t0 = time.perf_counter()

    if req.pipeline == "basic":
        from packages.rag.basic_rag import basic_rag
        result = basic_rag(req.question)
    else:
        from apps.api.graph import run_graph
        graph_result = run_graph(
            question=req.question,
            pipeline=req.pipeline,
        )
        result = {
            "answer": graph_result["answer"],
            "sources": graph_result["sources"],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "cost_usd": 0.0,
            "pipeline": req.pipeline,
        }

    result.setdefault("latency_ms", int((time.perf_counter() - t0) * 1000))
    result.setdefault("cost_usd", 0.0)

    return AskResponse(
        answer=result["answer"],
        sources=result["sources"],
        classification=result.get("classification"),
        latency_ms=result["latency_ms"],
        cost_usd=result["cost_usd"],
        pipeline=result["pipeline"],
    )

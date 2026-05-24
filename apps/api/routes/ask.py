import logging
import time
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
MAX_QUESTION_CHARS = 2_000
MAX_ATTACHMENT_CHARS = 20_000


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=MAX_QUESTION_CHARS * 4)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS)
    pipeline: Literal["basic", "advanced", "graph"] = "advanced"
    attachment_text: str = Field(default="", max_length=MAX_ATTACHMENT_CHARS)
    attachment_name: str | None = None
    # Prior conversation turns (oldest→newest), excluding the current question.
    history: list[Turn] = Field(default_factory=list, max_length=20)


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


class ExtractResponse(BaseModel):
    filename: str
    text: str
    method: str
    pages: int
    chars: int
    truncated: bool


@router.post("/extract", response_model=ExtractResponse)
async def extract(file: UploadFile = File(...)):
    """Extract text from an attached document (image/PDF/DOCX/txt) for use as context."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 15 МБ")

    from packages.multimodal import extract_document

    try:
        result = await run_in_threadpool(extract_document, file.filename or "file", data)
    except ValueError as e:
        raise HTTPException(status_code=415, detail=str(e))
    except Exception as e:
        logger.error("Document extraction failed for %s: %s", file.filename, e)
        raise HTTPException(status_code=502, detail="Не удалось извлечь текст из документа")
    return ExtractResponse(**result)


@router.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    t0 = time.perf_counter()

    history = [t.model_dump() for t in req.history]

    if req.pipeline == "basic":
        from packages.rag.basic_rag import basic_rag
        result = basic_rag(req.question, attachment_text=req.attachment_text, history=history)
    else:
        from apps.api.graph import run_graph
        graph_result = run_graph(
            question=req.question,
            pipeline=req.pipeline,
            attachment_text=req.attachment_text,
            history=history,
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

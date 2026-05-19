"""Document upload and processing endpoints."""
from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from apps.api.auth import get_current_user

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
}


class ExtractResponse(BaseModel):
    text: str
    filename: str
    pages: int


class CheckResponse(BaseModel):
    answer: str
    filename: str
    latency_ms: int


@router.post("/documents/extract", response_model=ExtractResponse)
async def extract_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Extract text from uploaded PDF/DOCX/image via LlamaParse."""
    content = await file.read()
    from packages.agents.doc_extractor import extract_from_bytes
    text = extract_from_bytes(content, file.filename or "document.pdf")
    pages = max(1, text.count("\n\n"))
    return ExtractResponse(text=text, filename=file.filename or "", pages=pages)


@router.post("/documents/check", response_model=CheckResponse)
async def check_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Extract text via LlamaParse then run doc_check through LangGraph."""
    import time
    t0 = time.perf_counter()

    content = await file.read()
    from packages.agents.doc_extractor import extract_from_bytes
    doc_text = extract_from_bytes(content, file.filename or "document.pdf")

    from apps.api.graph import run_graph
    result = run_graph(
        question="Проверь этот трудовой документ на соответствие ТК РК",
        pipeline="doc_check",
        doc_text=doc_text,
    )
    return CheckResponse(
        answer=result["answer"],
        filename=file.filename or "",
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )

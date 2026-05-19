"""Document extraction via LlamaParse (PDF/DOCX/OCR) with GPT-4.1 vision fallback."""
import asyncio
import base64
import io
import os
import tempfile
from pathlib import Path

from packages.config import settings


def _get_parser():
    from llama_cloud_services import LlamaParse
    return LlamaParse(
        api_key=settings.llama_cloud_api_key,
        result_type="markdown",
        verbose=False,
    )


def extract_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract text from uploaded file bytes using LlamaParse.

    Supports PDF, DOCX, XLSX, PNG, JPG, TIFF (including scanned docs).
    Falls back to GPT-4.1 vision for images if LlamaParse fails.
    """
    suffix = Path(filename).suffix.lower() or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        parser = _get_parser()
        docs = asyncio.run(parser.aload_data(tmp_path))
        text = "\n\n".join(d.text for d in docs if d.text)
        if text.strip():
            return text
    except Exception:
        pass
    finally:
        os.unlink(tmp_path)

    # Vision fallback for images
    if suffix in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
        return _vision_fallback(file_bytes, filename)

    return ""


def _vision_fallback(image_bytes: bytes, filename: str) -> str:
    """Use GPT-4.1 vision to extract text from an image."""
    from openai import OpenAI
    client = OpenAI(api_key=settings.openai_api_key)
    b64 = base64.b64encode(image_bytes).decode()
    ext = Path(filename).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "tiff": "image/tiff", "tif": "image/tiff"}.get(ext, "image/jpeg")
    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Извлеки весь текст из этого документа. Верни только текст, без комментариев."},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        max_tokens=4096,
    )
    return response.choices[0].message.content or ""

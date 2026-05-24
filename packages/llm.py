"""Central LLM client: OpenAI primary, Gemini fallback.

LLM completions fall back to Gemini (via its OpenAI-compatible endpoint) when
the OpenAI call fails. Embeddings do NOT live here and have no fallback — the
query vector must match the provider/dimension of the vectors already indexed
in Qdrant, so a cross-provider switch would require a full re-ingest (see
packages/rag/embeddings.py).
"""
import logging

from openai import AsyncOpenAI, OpenAI

from packages.config import settings

logger = logging.getLogger(__name__)

_primary: OpenAI | None = None
_fallback: OpenAI | None = None
_aprimary: AsyncOpenAI | None = None
_afallback: AsyncOpenAI | None = None


def _get_primary() -> OpenAI:
    global _primary
    if _primary is None:
        _primary = OpenAI(api_key=settings.openai_api_key)
    return _primary


def _get_fallback() -> OpenAI | None:
    global _fallback
    if _fallback is None and settings.gemini_api_key:
        _fallback = OpenAI(api_key=settings.gemini_api_key, base_url=settings.gemini_api_base)
    return _fallback


def _get_aprimary() -> AsyncOpenAI:
    global _aprimary
    if _aprimary is None:
        _aprimary = AsyncOpenAI(api_key=settings.openai_api_key)
    return _aprimary


def _get_afallback() -> AsyncOpenAI | None:
    global _afallback
    if _afallback is None and settings.gemini_api_key:
        _afallback = AsyncOpenAI(api_key=settings.gemini_api_key, base_url=settings.gemini_api_base)
    return _afallback


def chat_complete(*, model: str, fallback_model: str | None = None, **kwargs):
    """Chat completion via OpenAI; on any error retry once on Gemini.

    `model` is the OpenAI (primary) model. `fallback_model` defaults to
    settings.fallback_llm_model. Raises the original error if no Gemini key is set.
    """
    try:
        return _get_primary().chat.completions.create(model=model, **kwargs)
    except Exception as e:
        fb = _get_fallback()
        if fb is None:
            raise
        logger.warning("OpenAI primary failed (%s), falling back to Gemini", e)
        return fb.chat.completions.create(model=fallback_model or settings.fallback_llm_model, **kwargs)


async def achat_complete(*, model: str, fallback_model: str | None = None, **kwargs):
    """Async counterpart of chat_complete."""
    try:
        return await _get_aprimary().chat.completions.create(model=model, **kwargs)
    except Exception as e:
        fb = _get_afallback()
        if fb is None:
            raise
        logger.warning("OpenAI primary failed (%s), falling back to Gemini", e)
        return await fb.chat.completions.create(
            model=fallback_model or settings.fallback_llm_model, **kwargs
        )

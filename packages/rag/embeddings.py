from openai import OpenAI
from packages.config import settings

_client: OpenAI | None = None

MAX_CHARS = 5000  # text-embedding-004 limit: 2048 tokens; Cyrillic ~2.5 chars/token → 5000 safe


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.effective_llm_api_key,
            base_url=settings.llm_api_base,
        )
    return _client


def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    client = _get_client()
    model = model or settings.embedding_model
    results = []
    batch_size = 20  # Gemini embeddings API: up to 100 texts, keep small for reliability
    for i in range(0, len(texts), batch_size):
        batch = [t[:MAX_CHARS] if t and t.strip() else "." for t in texts[i : i + batch_size]]
        response = client.embeddings.create(input=batch, model=model)
        results.extend([d.embedding for d in response.data])
    return results


def embed_query(text: str, model: str | None = None) -> list[float]:
    return embed_texts([text], model)[0]

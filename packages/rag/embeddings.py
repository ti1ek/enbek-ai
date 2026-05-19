from openai import OpenAI
from packages.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


MAX_CHARS = 6000  # Cyrillic ≈ 1 char/token in cl100k_base; 8192 token limit → 6000 safe


def embed_texts(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    client = _get_client()
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = [t[:MAX_CHARS] for t in texts[i : i + batch_size]]
        response = client.embeddings.create(input=batch, model=model)
        results.extend([d.embedding for d in response.data])
    return results


def embed_query(text: str, model: str = "text-embedding-3-small") -> list[float]:
    return embed_texts([text], model)[0]

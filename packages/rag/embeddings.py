from openai import OpenAI
from packages.config import settings

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def embed_texts(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    client = _get_client()
    # Process in batches of 100 to stay within API limits
    results = []
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(input=batch, model=model)
        results.extend([d.embedding for d in response.data])
    return results


def embed_query(text: str, model: str = "text-embedding-3-small") -> list[float]:
    return embed_texts([text], model)[0]

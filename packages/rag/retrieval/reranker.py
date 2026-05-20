"""Cohere Rerank 3.5 — reranks retrieved chunks by relevance."""
import cohere
from packages.config import settings

_client: cohere.Client | None = None


def _get_client() -> cohere.Client:
    global _client
    if _client is None:
        _client = cohere.Client(api_key=settings.cohere_api_key)
    return _client


def rerank(query: str, documents: list[dict], top_n: int = 5) -> list[dict]:
    """Rerank documents using Cohere Rerank 3.5.

    Args:
        query: The search query.
        documents: List of dicts with at least "text" key (chunk payloads).
        top_n: Number of top results to return.

    Returns:
        Top-n documents sorted by rerank score, each with added "rerank_score".
    """
    if not documents:
        return []

    client = _get_client()
    doc_texts = [d.get("text", "") for d in documents]

    try:
        response = client.rerank(
            model="rerank-v3.5",
            query=query,
            documents=doc_texts,
            top_n=min(top_n, len(documents)),
        )
        reranked = []
        for result in response.results:
            doc = dict(documents[result.index])
            doc["rerank_score"] = result.relevance_score
            reranked.append(doc)
        return reranked
    except Exception:
        return documents[:top_n]

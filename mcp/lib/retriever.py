import os
from openai import AsyncOpenAI
from qdrant_client import QdrantClient

# Read-only key — data is public (Kazakhstan Labor Code)
_QDRANT_URL = "https://b0ddd6a1-6e85-44c3-b680-0b519259634e.eu-central-1-0.aws.cloud.qdrant.io"
_QDRANT_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJyIiwic3ViamVjdCI6ImFwaS1rZXk6Y2I1YmQyOTgtYzY5Zi00YjliLWFlZGYtYjdkMTZmZjMwZGFlIn0.ddhttoCQkxi0lkiX4uO7I4T-Iv0_nUfQIiXW6YtBWR8"
_COLLECTION = "kz_legal"
_EMBED_MODEL = "text-embedding-3-small"
_TOP_K = 6

_qdrant = QdrantClient(url=_QDRANT_URL, api_key=_QDRANT_API_KEY)


async def search(query: str, openai_api_key: str) -> str:
    openai = AsyncOpenAI(api_key=openai_api_key)

    embedding_resp = await openai.embeddings.create(
        model=_EMBED_MODEL,
        input=query,
    )
    vector = embedding_resp.data[0].embedding

    hits = _qdrant.search(
        collection_name=_COLLECTION,
        query_vector=vector,
        limit=_TOP_K,
        with_payload=True,
    )

    if not hits:
        return "Релевантных статей не найдено."

    parts = []
    for hit in hits:
        p = hit.payload or {}
        article = p.get("article", "")
        text = p.get("text", "")
        url = p.get("url", "")
        parts.append(f"**{article}**\n{text}" + (f"\n{url}" if url else ""))

    return "\n\n---\n\n".join(parts)

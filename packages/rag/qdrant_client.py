from functools import lru_cache
from qdrant_client import QdrantClient, models
from packages.config import settings

COLLECTION = settings.qdrant_collection
VECTOR_SIZE = 1536  # text-embedding-3-small


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection() -> None:
    client = get_qdrant()
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION in existing:
        return
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
        sparse_vectors_config={
            "text": models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
        optimizers_config=models.OptimizersConfigDiff(memmap_threshold=20000),
    )
    # Payload indices for filtering
    for field in ["source_type", "article"]:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    client.create_payload_index(
        collection_name=COLLECTION,
        field_name="in_force",
        field_schema=models.PayloadSchemaType.BOOL,
    )
    client.create_payload_index(
        collection_name=COLLECTION,
        field_name="redaction_date",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )


def upsert_chunks(points: list[models.PointStruct]) -> None:
    client = get_qdrant()
    client.upsert(collection_name=COLLECTION, points=points, wait=True)


def dense_search(
    query_vector: list[float],
    top_k: int = 10,
    source_types: list[str] | None = None,
    in_force_only: bool = True,
    redaction_year: int | None = None,
) -> list[models.ScoredPoint]:
    client = get_qdrant()
    filters = _build_filter(source_types, in_force_only, redaction_year)
    result = client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=top_k,
        query_filter=filters,
        with_payload=True,
    )
    return result.points


def hybrid_search(
    query_vector: list[float],
    sparse_vector: models.SparseVector,
    top_k: int = 10,
    source_types: list[str] | None = None,
    in_force_only: bool = True,
) -> list[models.ScoredPoint]:
    """Native Qdrant hybrid search via prefetch + RRF fusion."""
    client = get_qdrant()
    filters = _build_filter(source_types, in_force_only)
    results = client.query_points(
        collection_name=COLLECTION,
        prefetch=[
            models.Prefetch(query=query_vector, using="", limit=top_k * 3),
            models.Prefetch(query=sparse_vector, using="text", limit=top_k * 3),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
        query_filter=filters,
        with_payload=True,
    )
    return results.points


def _build_filter(
    source_types: list[str] | None,
    in_force_only: bool,
    redaction_year: int | None = None,
) -> models.Filter | None:
    """Build Qdrant filter.

    redaction_year: if set (e.g. 2022), search historical versions matching that year
                    instead of applying in_force_only filter.
    """
    conditions = []

    if redaction_year:
        # Historical query: match chunks whose redaction_date starts with that year
        conditions.append(models.FieldCondition(
            key="redaction_date",
            match=models.MatchText(text=str(redaction_year)),
        ))
    elif in_force_only:
        conditions.append(models.FieldCondition(
            key="in_force",
            match=models.MatchValue(value=True),
        ))

    if source_types:
        conditions.append(models.FieldCondition(
            key="source_type",
            match=models.MatchAny(any=source_types),
        ))
    if not conditions:
        return None
    return models.Filter(must=conditions)


def count_points() -> int:
    client = get_qdrant()
    return client.count(collection_name=COLLECTION).count

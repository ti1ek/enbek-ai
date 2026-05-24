"""Populate BM25 sparse vectors for all points in Qdrant.

Uses Qdrant/bm25 via fastembed — language-agnostic, works for Russian text.
The collection must already have sparse_vectors_config {"text": SparseVectorParams(modifier=IDF)}.

Run:
    uv run python scripts/build_sparse_vectors.py
"""
import time
from qdrant_client import models
from fastembed import SparseTextEmbedding

from packages.rag.qdrant_client import get_qdrant
from packages.config import settings

BATCH_SIZE = 200
COLLECTION = settings.qdrant_collection


def main() -> None:
    client = get_qdrant()
    encoder = SparseTextEmbedding(model_name="Qdrant/bm25")

    total = client.count(collection_name=COLLECTION).count
    print(f"Total points: {total}")

    done = 0
    offset = None
    t0 = time.perf_counter()

    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=["text"],
            with_vectors=False,
        )
        if not batch:
            break

        texts = [(p.id, (p.payload or {}).get("text") or "") for p in batch]
        raw_texts = [t for _, t in texts]

        sparse_vecs = list(encoder.embed(raw_texts))

        points_vectors = []
        for (point_id, _), sv in zip(texts, sparse_vecs):
            points_vectors.append(models.PointVectors(
                id=point_id,
                vector={"text": models.SparseVector(
                    indices=sv.indices.tolist(),
                    values=sv.values.tolist(),
                )},
            ))

        client.update_vectors(
            collection_name=COLLECTION,
            points=points_vectors,
        )

        done += len(batch)
        elapsed = time.perf_counter() - t0
        rate = done / elapsed
        remaining = (total - done) / rate if rate > 0 else 0
        print(f"  {done}/{total} ({done/total*100:.1f}%) | {rate:.0f} pts/s | ETA {remaining/60:.1f} min")

        if offset is None:
            break

    print(f"\nDone. {done} points indexed in {(time.perf_counter()-t0)/60:.1f} min.")


if __name__ == "__main__":
    main()

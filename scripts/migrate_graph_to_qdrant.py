"""Migrate cross-doc graph edges from JSON → Qdrant payload.

Reads data/chunks/cross_doc_edges.json and sets linked_chunks: [uuid, ...]
on each source chunk in Qdrant. Source chunks are matched by doc_id + article.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, SetPayload, PointIdsList
from packages.config import settings
from rich.console import Console
from rich.progress import track

console = Console()
EDGES_FILE = Path("data/chunks/cross_doc_edges.json")


def main():
    edges = json.loads(EDGES_FILE.read_text())
    console.print(f"[bold blue]Loaded {len(edges)} edges from {EDGES_FILE}")

    # Group target_chunk_ids by (source_doc_id, source_article)
    source_to_targets: dict[tuple, list[str]] = defaultdict(list)
    for e in edges:
        key = (e["source_doc_id"], str(e["source_article"]))
        source_to_targets[key].append(e["target_chunk_id"])

    console.print(f"Unique source (doc_id, article) pairs: {len(source_to_targets)}")

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    updated = 0
    skipped = 0

    for (doc_id, article), target_ids in track(source_to_targets.items(), description="Updating Qdrant..."):
        # Find all chunks matching this doc_id + article
        try:
            pts, _ = client.scroll(
                settings.qdrant_collection,
                scroll_filter=Filter(must=[
                    FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                    FieldCondition(key="article", match=MatchValue(value=article)),
                ]),
                limit=50,
                with_payload=False,
                with_vectors=False,
            )
        except Exception as e:
            console.print(f"  [yellow]Skip ({doc_id}, art.{article}): {e}")
            skipped += 1
            continue

        if not pts:
            skipped += 1
            continue

        chunk_ids = [p.id for p in pts]
        client.set_payload(
            collection_name=settings.qdrant_collection,
            payload={"linked_chunks": list(set(target_ids))},
            points=PointIdsList(points=chunk_ids),
        )
        updated += len(chunk_ids)

    console.print(f"\n[bold green]Done! Updated {updated} chunks, skipped {skipped} source keys")

    # Verify one sample
    pts, _ = client.scroll(
        settings.qdrant_collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="doc_id", match=MatchValue(value=edges[0]["source_doc_id"])),
            FieldCondition(key="article", match=MatchValue(value=str(edges[0]["source_article"]))),
        ]),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if pts:
        linked = pts[0].payload.get("linked_chunks", [])
        console.print(f"Sample verification — chunk {pts[0].id}: linked_chunks = {linked[:3]}...")


if __name__ == "__main__":
    main()

"""One-shot: scan all chunks in Qdrant, run citation_extractor, save edges sidecar.

Output: data/chunks/citation_edges.json — list[edge_dict].

Idempotent: re-run overwrites the file. Does NOT modify the Qdrant collection.
Safe to delete the output to roll back.
"""
import json
from pathlib import Path

from packages.rag.ingestion.citation_extractor import extract_citations
from packages.rag.qdrant_client import COLLECTION, get_qdrant

OUTPUT = Path("data/chunks/citation_edges.json")


def main() -> None:
    client = get_qdrant()
    next_offset = None
    edges_all: list[dict] = []
    scanned = 0
    with_edges = 0

    while True:
        batch, next_offset = client.scroll(
            collection_name=COLLECTION,
            limit=512,
            offset=next_offset,
            with_payload=True,
            with_vectors=False,
        )
        if not batch:
            break
        for p in batch:
            scanned += 1
            chunk = {"id": p.id, **(p.payload or {})}
            edges = extract_citations(chunk)
            if edges:
                with_edges += 1
                edges_all.extend(edges)
        if next_offset is None:
            break

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(edges_all, ensure_ascii=False), encoding="utf-8")

    print(f"Scanned {scanned} chunks; {with_edges} have ≥1 citation; total edges: {len(edges_all)}")
    print(f"Saved → {OUTPUT}")

    # Quick summary by edge_type
    by_type: dict[str, int] = {}
    for e in edges_all:
        by_type[e["edge_type"]] = by_type.get(e["edge_type"], 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()

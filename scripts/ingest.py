"""One-command ingestion: scrape → chunk → embed → upsert to Qdrant."""
import asyncio
import json
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.progress import track

console = Console()
DATA_DIR = Path("data/chunks")


def load_all_chunks() -> list[dict]:
    chunks = []
    for path in DATA_DIR.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            chunks.extend(data)
        console.print(f"  Loaded {len(data)} records from {path.name}")
    return chunks


async def main(skip_scrape: bool = False, fresh: bool = False, skip_tag: bool = False) -> None:
    console.rule("[bold blue]Enbek AI — Ingestion Pipeline")

    # Step 1: Scrape
    if not skip_scrape:
        console.print("\n[bold]Шаг 1: Скрапинг источников...")
        from packages.rag.ingestion.scrape_adilet import scrape_all
        from packages.rag.ingestion.scrape_dialog_egov import scrape_dialog_egov
        from packages.rag.ingestion.scrape_adilet_history import scrape_historical
        from packages.rag.ingestion.scrape_govkz_methodology import scrape_all_methodology
        from packages.rag.ingestion.scrape_tkrk import scrape_tkrk

        await scrape_all()
        await scrape_dialog_egov()
        await scrape_historical()
        await scrape_all_methodology()
        await scrape_tkrk()
    else:
        console.print("[yellow]Пропускаем скрапинг (--skip-scrape)")

    # Step 2: Load all raw chunks
    console.print("\n[bold]Шаг 2: Загрузка чанков...")
    chunks = load_all_chunks()
    if not chunks:
        console.print("[red]Нет данных для ингестии. Запустите скрапинг.")
        sys.exit(1)
    console.print(f"[green]Всего чанков: {len(chunks)}")

    # Step 2b: Enrich with metadata (doc_type, year, chunk_type) — deterministic
    from packages.rag.ingestion.metadata import enrich, tag_topics_llm
    for c in chunks:
        enrich(c)
    console.print("[green]doc_type / year / chunk_type добавлены")

    # Step 2c: LLM topic tagging (GPT-4.1-mini, batched)
    if skip_tag:
        console.print("[yellow]Пропускаем topic tagging (--skip-tag)")
    else:
        console.print("\n[bold]Шаг 2c: LLM topic tagging...")
        await tag_topics_llm(chunks)
        console.print("[green]topic добавлены")

    # Step 3: Prepare Qdrant collection
    console.print("\n[bold]Шаг 3: Подготовка Qdrant коллекции...")
    from packages.rag.qdrant_client import ensure_collection, recreate_collection
    if fresh:
        recreate_collection()
        console.print("[yellow]Коллекция пересоздана (--fresh)")
    else:
        ensure_collection()
    console.print("[green]Коллекция kz_legal готова")

    # Step 4: Embed and upsert
    console.print(f"\n[bold]Шаг 4: Эмбеддинги + загрузка в Qdrant...")
    from packages.rag.embeddings import embed_texts
    from packages.rag.qdrant_client import upsert_chunks
    from qdrant_client import models

    batch_size = 50
    total = 0

    for i in track(range(0, len(chunks), batch_size), description="Uploading..."):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]

        # Get embeddings
        vectors = embed_texts(texts)

        # Build Qdrant points
        points = []
        for chunk, vector in zip(batch, vectors):
            payload = {k: v for k, v in chunk.items() if k != "chunk_id"}
            # Truncate large text fields to stay within Qdrant 32MB payload limit
            if payload.get("parent_text") and len(payload["parent_text"]) > 8000:
                payload["parent_text"] = payload["parent_text"][:8000]
            if payload.get("text") and len(payload["text"]) > 4000:
                payload["text"] = payload["text"][:4000]
            points.append(models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"])),
                vector=vector,
                payload=payload,
            ))

        upsert_chunks(points)
        total += len(points)

    # Step 5: Verify
    from packages.rag.qdrant_client import count_points
    final_count = count_points()
    console.print(f"\n[bold green]✓ Ингестия завершена. Точек в Qdrant: {final_count}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-scrape", action="store_true", help="Use existing data/chunks files")
    parser.add_argument("--skip-tag", action="store_true", help="Skip LLM topic tagging")
    parser.add_argument("--fresh", action="store_true", help="Drop and recreate Qdrant collection before ingestion")
    args = parser.parse_args()
    asyncio.run(main(skip_scrape=args.skip_scrape, fresh=args.fresh, skip_tag=args.skip_tag))

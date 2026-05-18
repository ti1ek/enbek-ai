"""One-command ingestion: scrape → chunk → embed → upsert to Qdrant."""
import asyncio
import json
import sys
import uuid
from pathlib import Path

from rich.console import Console
from rich.progress import track

console = Console()
DATA_DIR = Path("data/raw")


def load_all_chunks() -> list[dict]:
    chunks = []
    for path in DATA_DIR.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            chunks.extend(data)
        console.print(f"  Loaded {len(data)} records from {path.name}")
    return chunks


async def main(skip_scrape: bool = False) -> None:
    console.rule("[bold blue]Enbek AI — Ingestion Pipeline")

    # Step 1: Scrape
    if not skip_scrape:
        console.print("\n[bold]Шаг 1: Скрапинг источников...")
        from packages.rag.ingestion.scrape_adilet import scrape_all
        from packages.rag.ingestion.scrape_dialog_egov import scrape_dialog_egov

        await scrape_all()
        await scrape_dialog_egov()
    else:
        console.print("[yellow]Пропускаем скрапинг (--skip-scrape)")

    # Step 2: Load all raw chunks
    console.print("\n[bold]Шаг 2: Загрузка чанков...")
    chunks = load_all_chunks()
    if not chunks:
        console.print("[red]Нет данных для ингестии. Запустите скрапинг.")
        sys.exit(1)
    console.print(f"[green]Всего чанков: {len(chunks)}")

    # Step 3: Ensure Qdrant collection exists
    console.print("\n[bold]Шаг 3: Подготовка Qdrant коллекции...")
    from packages.rag.qdrant_client import ensure_collection
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
            points.append(models.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"])),
                vector=vector,
                payload={k: v for k, v in chunk.items() if k != "chunk_id"},
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
    parser.add_argument("--skip-scrape", action="store_true", help="Use existing data/raw files")
    args = parser.parse_args()
    asyncio.run(main(skip_scrape=args.skip_scrape))

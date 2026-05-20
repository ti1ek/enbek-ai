"""Tag chunks that have empty topic field in Qdrant.

Scrolls Qdrant for points with topic=[], runs LLM tagging,
updates payload in-place without re-embedding.
"""
import asyncio
from rich.console import Console

console = Console()


async def main() -> None:
    from packages.config import settings
    from packages.rag.qdrant_client import get_qdrant, COLLECTION
    from packages.rag.ingestion.metadata import tag_topics_llm

    client = get_qdrant()

    console.print("[bold]Сканируем Qdrant на чанки без топиков...")

    # Scroll all points with empty topic
    missing: list[dict] = []
    offset = None

    while True:
        results, next_offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=None,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in results:
            payload = point.payload or {}
            topics = payload.get("topic", None)
            if topics is None or topics == []:
                missing.append({"_qdrant_id": str(point.id), **payload})

        if next_offset is None:
            break
        offset = next_offset

    console.print(f"Чанков без топиков: {len(missing)}")
    if not missing:
        console.print("[green]Все чанки уже тегированы!")
        return

    # Run LLM topic tagging in-place
    await tag_topics_llm(missing)

    # Update payload in Qdrant
    console.print("[bold]Обновляем payload в Qdrant...")
    updated = 0
    for chunk in missing:
        qid = chunk.pop("_qdrant_id")
        if chunk.get("topic"):
            client.set_payload(
                collection_name=COLLECTION,
                payload={"topic": chunk["topic"]},
                points=[qid],
            )
            updated += 1

    console.print(f"[bold green]✓ Обновлено {updated} чанков из {len(missing)}")


if __name__ == "__main__":
    asyncio.run(main())

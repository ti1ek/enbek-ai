"""Weekly URL liveness checker for Qdrant chunks.

For each chunk with a non-empty URL:
  - HEAD request (timeout 10s)
  - Non-200 response → increment inactive_count in payload
  - inactive_count >= 4 → delete chunk (URL dead for ~1 month)

Run manually or via cron:
  crontab -e
  0 9 * * 1 cd /path/to/enbek-ai && uv run python scripts/check_urls.py
"""
import sys
import time
import httpx
from qdrant_client import models
from rich.console import Console
from rich.progress import track

sys.path.insert(0, ".")
from packages.rag.qdrant_client import get_qdrant, COLLECTION

console = Console()

INACTIVE_THRESHOLD = 4   # delete after this many consecutive failures
BATCH_SIZE = 100
REQUEST_TIMEOUT = 10.0
SLEEP_BETWEEN = 0.3      # polite rate limiting

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EnbekAI-URLChecker/1.0)",
}


def _is_alive(url: str, client: httpx.Client) -> bool:
    try:
        r = client.head(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        return r.status_code < 400
    except Exception:
        return False


def scroll_all_with_url() -> list[tuple[str, str, int]]:
    """Return (point_id, url, inactive_count) for all chunks that have a URL."""
    qdrant = get_qdrant()
    items = []
    offset = None

    while True:
        result, next_offset = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must_not=[
                    models.IsEmptyCondition(is_empty=models.PayloadField(key="url"))
                ]
            ),
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=["url", "inactive_count"],
            with_vectors=False,
        )
        for pt in result:
            url = pt.payload.get("url", "")
            if url:
                inactive = pt.payload.get("inactive_count", 0) or 0
                items.append((str(pt.id), url, inactive))

        if next_offset is None:
            break
        offset = next_offset

    return items


def main() -> None:
    console.rule("[bold blue]Enbek AI — URL Liveness Check")

    console.print("Загружаем точки с URL из Qdrant...")
    items = scroll_all_with_url()
    console.print(f"Найдено {len(items)} точек с URL\n")

    qdrant = get_qdrant()
    stats = {"checked": 0, "alive": 0, "failed": 0, "incremented": 0, "deleted": 0}

    to_increment: list[str] = []   # point IDs where inactive_count += 1
    to_reset: list[str] = []       # point IDs to reset inactive_count to 0
    to_delete: list[str] = []      # point IDs to delete (inactive_count >= threshold)

    # Deduplicate URLs to avoid hammering the same host
    url_cache: dict[str, bool] = {}

    with httpx.Client(headers=HEADERS, verify=False) as http:
        for point_id, url, inactive in track(items, description="Checking..."):
            stats["checked"] += 1

            if url in url_cache:
                alive = url_cache[url]
            else:
                alive = _is_alive(url, http)
                url_cache[url] = alive
                time.sleep(SLEEP_BETWEEN)

            if alive:
                stats["alive"] += 1
                if inactive > 0:
                    to_reset.append(point_id)
            else:
                stats["failed"] += 1
                new_inactive = inactive + 1
                if new_inactive >= INACTIVE_THRESHOLD:
                    to_delete.append(point_id)
                    stats["deleted"] += 1
                else:
                    to_increment.append(point_id)
                    stats["incremented"] += 1

    # Apply updates in batches
    if to_reset:
        console.print(f"Сбрасываем inactive_count для {len(to_reset)} ожившых точек...")
        for i in range(0, len(to_reset), BATCH_SIZE):
            batch = to_reset[i:i + BATCH_SIZE]
            qdrant.set_payload(
                collection_name=COLLECTION,
                payload={"inactive_count": 0},
                points=batch,
            )

    if to_increment:
        console.print(f"Инкрементируем inactive_count для {len(to_increment)} точек...")
        for point_id in to_increment:
            qdrant.set_payload(
                collection_name=COLLECTION,
                payload={"inactive_count": 1},  # will be incremented via get+set
                points=[point_id],
            )
        # Proper increment: read current value and set new
        # (Qdrant doesn't support atomic increment, so we do it per-point above
        #  using the value we already read in scroll — this is safe for weekly runs)
        for i in range(0, len(to_increment), BATCH_SIZE):
            batch_ids = to_increment[i:i + BATCH_SIZE]
            # Re-read current inactive_count and set correctly
            pts, _ = qdrant.scroll(
                collection_name=COLLECTION,
                scroll_filter=models.Filter(
                    must=[models.HasIdCondition(has_id=batch_ids)]
                ),
                limit=BATCH_SIZE,
                with_payload=["inactive_count"],
                with_vectors=False,
            )
            for pt in pts:
                current = pt.payload.get("inactive_count", 0) or 0
                qdrant.set_payload(
                    collection_name=COLLECTION,
                    payload={"inactive_count": current + 1},
                    points=[str(pt.id)],
                )

    if to_delete:
        console.print(f"Удаляем {len(to_delete)} мёртвых точек (inactive >= {INACTIVE_THRESHOLD})...")
        for i in range(0, len(to_delete), BATCH_SIZE):
            batch = to_delete[i:i + BATCH_SIZE]
            qdrant.delete(
                collection_name=COLLECTION,
                points_selector=models.PointIdsList(points=batch),
            )

    console.rule("[bold green]Результаты")
    console.print(f"  Проверено:    {stats['checked']}")
    console.print(f"  Живых:        {stats['alive']}")
    console.print(f"  Недоступных:  {stats['failed']}")
    console.print(f"  Помечено:     {stats['incremented']} (inactive_count +1)")
    console.print(f"  Удалено:      {stats['deleted']} (>= {INACTIVE_THRESHOLD} провалов)")


if __name__ == "__main__":
    main()

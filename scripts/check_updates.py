"""Monthly update checker for all Enbek AI data sources.

Two types of checks:
  1. Adilet documents — compare "по состоянию на DD.MM.YYYY" with stored redaction_date.
     If newer → mark old chunks in_force=False, re-scrape with --rescrape flag.

  2. dialog.egov.kz Q&A — no edits to existing answers, but new Q&A pairs appear.
     Collect all live question IDs → find IDs absent from Qdrant → add them.

Run monthly:
  uv run python scripts/check_updates.py
  uv run python scripts/check_updates.py --rescrape   # also re-ingest stale adilet docs
  uv run python scripts/check_updates.py --add-new-qa  # also add new dialog.egov Q&A

Cron:
  0 9 1 * * cd /path/to/enbek-ai && uv run python scripts/check_updates.py --rescrape --add-new-qa
"""
import asyncio
import hashlib
import re
import sys
import uuid
from datetime import date

import httpx
from rich.console import Console
from rich.table import Table

sys.path.insert(0, ".")

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,kk;q=0.8",
}

_REDACTION_RE = re.compile(
    r"по\s+состоянию\s+на\s+(\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_iso(ddmmyyyy: str) -> str:
    d, m, y = ddmmyyyy.split(".")
    return f"{y}-{m}-{d}"


def _parse_live_date(html: str) -> str | None:
    matches = _REDACTION_RE.findall(html)
    if not matches:
        return None
    return _to_iso(matches[-1])


async def _fetch(client: httpx.AsyncClient, url: str, params: dict | None = None) -> str | None:
    try:
        r = await client.get(url, params=params, timeout=30.0)
        r.raise_for_status()
        return r.text
    except Exception as e:
        console.print(f"[red]  Error fetching {url}: {e}")
        return None


def _embed_and_upsert(chunks: list[dict]) -> int:
    from packages.rag.embeddings import embed_texts
    from packages.rag.qdrant_client import upsert_chunks
    from qdrant_client import models as qmodels

    texts = [c["text"] for c in chunks]
    vectors = embed_texts(texts)

    points = []
    for chunk, vector in zip(chunks, vectors):
        points.append(qmodels.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk["chunk_id"])),
            vector=vector,
            payload={k: v for k, v in chunk.items() if k != "chunk_id"},
        ))

    batch_size = 50
    for i in range(0, len(points), batch_size):
        upsert_chunks(points[i:i + batch_size])

    return len(points)


# ══════════════════════════════════════════════════════════════════════════════
# Part 1 — Adilet document freshness
# ══════════════════════════════════════════════════════════════════════════════

def _get_stored_redaction_date(doc_id: str) -> str | None:
    from packages.rag.qdrant_client import get_qdrant, COLLECTION
    from qdrant_client import models

    qdrant = get_qdrant()
    result, _ = qdrant.scroll(
        collection_name=COLLECTION,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id)),
                models.FieldCondition(key="in_force", match=models.MatchValue(value=True)),
            ]
        ),
        limit=1,
        with_payload=["redaction_date"],
        with_vectors=False,
    )
    if not result:
        return None
    return result[0].payload.get("redaction_date") or None


def _mark_stale(doc_id: str, superseded_date: str) -> int:
    from packages.rag.qdrant_client import get_qdrant, COLLECTION
    from qdrant_client import models

    qdrant = get_qdrant()
    updated = 0
    offset = None

    while True:
        batch, next_offset = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id)),
                    models.FieldCondition(key="in_force", match=models.MatchValue(value=True)),
                ]
            ),
            limit=100,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        if not batch:
            break
        ids = [str(pt.id) for pt in batch]
        qdrant.set_payload(
            collection_name=COLLECTION,
            payload={"in_force": False, "superseded_date": superseded_date},
            points=ids,
        )
        updated += len(ids)
        if next_offset is None:
            break
        offset = next_offset

    return updated


async def _rescrape_and_upsert(meta: dict, client: httpx.AsyncClient) -> int:
    from packages.rag.ingestion.scrape_adilet import scrape_document

    chunks = await scrape_document(meta, client)
    if not chunks:
        return 0
    return _embed_and_upsert(chunks)


async def check_adilet_docs(
    rescrape: bool,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Check all adilet documents for updates. Returns (stale, fresh, unreachable)."""
    from packages.rag.ingestion.scrape_adilet import DOCUMENTS, LAWS, GOVT_DECREES, MINISTERIAL_ORDERS

    all_docs = list(DOCUMENTS.values()) + LAWS + GOVT_DECREES + MINISTERIAL_ORDERS
    stale, fresh, unreachable = [], [], []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
        for meta in all_docs:
            doc_id = meta["doc_id"]
            url = meta["url"]
            name = meta["name"]

            html = await _fetch(client, url)
            if not html:
                unreachable.append({"doc_id": doc_id, "name": name, "url": url})
                await asyncio.sleep(1.0)
                continue

            live_date = _parse_live_date(html)
            stored_date = _get_stored_redaction_date(doc_id)

            entry = {
                "doc_id": doc_id,
                "name": name,
                "url": url,
                "stored_date": stored_date or "(not in Qdrant)",
                "live_date": live_date or "(not found)",
                "meta": meta,
            }

            if not live_date or live_date <= (stored_date or ""):
                fresh.append(entry)
            else:
                stale.append(entry)

            await asyncio.sleep(1.0)

    if rescrape and stale:
        console.rule("[bold yellow]Re-ingesting stale adilet documents")
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
            for s in stale:
                doc_id = s["doc_id"]
                live_date = s["live_date"]
                console.print(f"\n[bold]{s['name']}[/bold] ({doc_id})")

                if s["stored_date"] != "(not in Qdrant)":
                    n = _mark_stale(doc_id, live_date)
                    console.print(f"  Marked {n} old chunks in_force=False")

                meta = dict(s["meta"])
                meta["redaction_date"] = live_date
                n_new = await _rescrape_and_upsert(meta, client)
                console.print(f"  Upserted {n_new} fresh chunks (redaction_date={live_date})")
                await asyncio.sleep(2.0)

    return stale, fresh, unreachable


# ══════════════════════════════════════════════════════════════════════════════
# Part 2 — dialog.egov.kz new Q&A
# ══════════════════════════════════════════════════════════════════════════════

DIALOG_LISTING_URL = "https://dialog.egov.kz/blogs/all-questions"
DIALOG_LISTING_PARAMS = {"categoryBlogFilter": "2", "answeredFilter": "yes"}
DIALOG_MAX_PAGES = 1210


def _get_stored_dialog_ids() -> set[str]:
    """Return all question_ids already stored in Qdrant for doc_id=dialog_egov."""
    from packages.rag.qdrant_client import get_qdrant, COLLECTION
    from qdrant_client import models

    qdrant = get_qdrant()
    ids: set[str] = set()
    offset = None

    while True:
        batch, next_offset = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id", match=models.MatchValue(value="dialog_egov")
                    )
                ]
            ),
            limit=500,
            offset=offset,
            with_payload=["question_id"],
            with_vectors=False,
        )
        for pt in batch:
            qid = pt.payload.get("question_id")
            if qid:
                ids.add(str(qid))
        if next_offset is None:
            break
        offset = next_offset

    return ids


async def _collect_new_dialog_ids(
    client: httpx.AsyncClient, known_ids: set[str]
) -> list[str]:
    """Paginate listing until we hit a page with only known IDs. Return new IDs."""
    new_ids: list[str] = []
    seen: set[str] = set()

    for page in range(1, DIALOG_MAX_PAGES + 1):
        params = {**DIALOG_LISTING_PARAMS, "page": str(page)}
        html = await _fetch(client, DIALOG_LISTING_URL, params)
        if not html:
            break

        page_ids = re.findall(r'href="/blogs/all-questions/(\d+)"', html)
        page_new = [qid for qid in page_ids if qid not in seen and qid not in known_ids]

        if not page_new and page > 1:
            # Reached IDs we already have — stop
            console.print(f"  Page {page}: all IDs known — stopping")
            break

        for qid in page_ids:
            seen.add(qid)
        new_ids.extend(page_new)

        if page_new:
            console.print(f"  Page {page}: +{len(page_new)} new IDs (total new: {len(new_ids)})")
        await asyncio.sleep(0.5)

    return new_ids


async def check_dialog_egov_new_qa(add_new: bool) -> int:
    """Check for new Q&A on dialog.egov.kz. Returns count of new items found."""
    import urllib3
    urllib3.disable_warnings()

    console.rule("[bold blue]dialog.egov.kz — checking for new Q&A")

    stored_ids = _get_stored_dialog_ids()
    console.print(f"  Stored in Qdrant: {len(stored_ids)} question IDs")

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
        new_ids = await _collect_new_dialog_ids(client, stored_ids)

        if not new_ids:
            console.print("[green]  No new Q&A found.")
            return 0

        console.print(f"[yellow]  Found {len(new_ids)} new question IDs")

        if not add_new:
            console.print("  Run with --add-new-qa to add them to Qdrant.")
            return len(new_ids)

        # Fetch and add new Q&A
        from packages.rag.ingestion.scrape_dialog_egov import (
            fetch_question_page, _is_labor_relevant,
        )

        sem = asyncio.Semaphore(5)
        new_chunks: list[dict] = []

        async def fetch_one(qid: str):
            async with sem:
                result = await fetch_question_page(qid, client)
                await asyncio.sleep(0.3)
                return result

        tasks = [fetch_one(qid) for qid in new_ids]
        for coro in asyncio.as_completed(tasks):
            qa = await coro
            if not qa:
                continue

            lines = []
            if qa.get("prev_question"):
                lines.append(f"Предыдущий вопрос: {qa['prev_question']}")
            lines.append(f"Вопрос: {qa['question']}")
            responder = qa.get("responder") or "Министерство труда РК"
            lines.append(f"Ответ ({responder}): {qa['answer']}")
            text = "\n".join(lines)

            from packages.rag.ingestion.scrape_dialog_egov import _to_iso
            new_chunks.append({
                "chunk_id": f"dialog_egov_{qa['question_id']}",
                "parent_id": f"dialog_egov_{qa['question_id']}",
                "text": text,
                "parent_text": text,
                "source_type": "mintrud_dialog",
                "doc_id": "dialog_egov",
                "article": "",
                "paragraph": "",
                "redaction_date": _to_iso(qa.get("answer_date", "")),
                "in_force": True,
                "url": qa["url"],
                "doc_name": "Открытый диалог — Министерство труда РК",
                "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                "responder": qa.get("responder", ""),
                "question_id": qa["question_id"],
            })

        if new_chunks:
            n = _embed_and_upsert(new_chunks)
            console.print(f"[green]  Added {n} new Q&A chunks to Qdrant")
        else:
            console.print("[yellow]  New IDs found but none passed labor relevance filter")

        return len(new_ids)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

async def main(rescrape: bool = False, add_new_qa: bool = False) -> None:
    import urllib3
    urllib3.disable_warnings()

    console.rule("[bold blue]Enbek AI — Monthly Update Check")
    console.print(f"Date: {date.today().isoformat()}\n")

    # ── 1. Adilet documents ───────────────────────────────────────────────────
    console.rule("Adilet documents")
    stale, fresh, unreachable = await check_adilet_docs(rescrape)

    table = Table(title="Adilet Document Freshness", show_lines=True)
    table.add_column("Doc ID", style="cyan", no_wrap=True)
    table.add_column("Name", max_width=38)
    table.add_column("Stored", justify="center")
    table.add_column("Live", justify="center")
    table.add_column("Status", justify="center")

    for s in stale:
        table.add_row(s["doc_id"], s["name"], s["stored_date"], s["live_date"], "[red]STALE")
    for s in fresh:
        table.add_row(s["doc_id"], s["name"], s["stored_date"], s["live_date"], "[green]OK")
    for s in unreachable:
        table.add_row(s["doc_id"], s["name"], "?", "(unreachable)", "[yellow]UNREACHABLE")

    console.print(table)
    console.print(
        f"Adilet: [red]{len(stale)} stale[/]  "
        f"[green]{len(fresh)} ok[/]  "
        f"[yellow]{len(unreachable)} unreachable[/]"
    )
    if stale and not rescrape:
        console.print("[yellow]  → Run with --rescrape to update stale documents")

    # ── 2. dialog.egov.kz new Q&A ─────────────────────────────────────────────
    console.print()
    new_qa_count = await check_dialog_egov_new_qa(add_new_qa)
    if new_qa_count and not add_new_qa:
        console.print("[yellow]  → Run with --add-new-qa to add them to Qdrant")

    console.rule("[bold green]Done")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Monthly update checker for all Enbek AI sources")
    parser.add_argument("--rescrape", action="store_true",
                        help="Re-ingest stale adilet docs (mark old in_force=False, upsert fresh)")
    parser.add_argument("--add-new-qa", action="store_true",
                        help="Fetch and add new dialog.egov.kz Q&A to Qdrant")
    args = parser.parse_args()
    asyncio.run(main(rescrape=args.rescrape, add_new_qa=args.add_new_qa))

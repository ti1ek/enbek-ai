"""Scrape historical redactions of KZ laws from adilet.zan.kz.

Ingests selected snapshots (-3 years) tagged with redaction_date and in_force=False.
Current version stays in_force=True; historical allow answering "what was the law in 2022".

Selected redactions:
  ТК РК (K1500000414):
    27.06.2022, 04.07.2023, 01.01.2024

  Социальный кодекс (K2300000224):
    20.04.2023 (первая редакция), 04.07.2023, 01.01.2024

  НП ВС РК № 9 (2017) — утратило силу 28.11.2024, заменено на № 1/2024.
    Хранится как in_force=False для исторического контекста.
"""
import asyncio
import hashlib
import json
from pathlib import Path

import httpx
from packages.rag.ingestion.scrape_adilet import fetch_page, parse_adilet_doc, DOCUMENTS

DATA_DIR = Path("data/chunks")
BASE_URL = "https://adilet.zan.kz"

HISTORICAL = [
    ("K1500000414", "27.06.2022", "labor_code"),
    ("K1500000414", "04.07.2023", "labor_code"),
    ("K1500000414", "01.01.2024", "labor_code"),
    ("K2300000224", "20.04.2023", "social_code"),
    ("K2300000224", "04.07.2023", "social_code"),
    ("K2300000224", "01.01.2024", "social_code"),
]

# НП ВС которые утратили силу — хранятся отдельно с явными метаданными
SUPERSEDED_DECREES = [
    {
        "doc_id": "P170000009S",
        "url": f"{BASE_URL}/rus/docs/P170000009S",
        "source_type": "sc_decree",
        "name": "НП ВС РК № 9 от 06.10.2017 о трудовых спорах (утратило силу)",
        "redaction_date": "2017-10-06",
        "in_force": False,
        "superseded_by": "P240000001S",  # НП ВС №1/2024
        "superseded_date": "2024-11-28",
    },
]

DOC_NAMES = {
    "K1500000414": "Трудовой кодекс РК",
    "K2300000224": "Социальный кодекс РК",
}


def _date_to_iso(date_str: str) -> str:
    d, m, y = date_str.split(".")
    return f"{y}-{m}-{d}"


async def scrape_historical() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False) as client:
        import urllib3
        urllib3.disable_warnings()

        for doc_id, archive_date, source_type in HISTORICAL:
            archive_url = f"{BASE_URL}/rus/archive/docs/{doc_id}/{archive_date}"
            iso_date = _date_to_iso(archive_date)
            doc_name = DOC_NAMES.get(doc_id, doc_id)
            print(f"\nScraping {doc_id} @ {archive_date}")

            html = await fetch_page(client, archive_url)
            if not html:
                print(f"  SKIP — could not fetch {archive_url}")
                await asyncio.sleep(2.0)
                continue

            meta = {
                "doc_id": doc_id,
                "source_type": source_type,
                "name": doc_name,
                "redaction_date": iso_date,
                "in_force": False,
                "url": f"{BASE_URL}/rus/docs/{doc_id}",
                "whitelist_articles": [],
            }

            raw_articles = parse_adilet_doc(html, meta)
            chunks = []
            for art in raw_articles:
                if art["article"] == "0":
                    continue
                parent_text = f"Статья {art['article']}. {art['title']}\n\n" + "\n".join(art["paragraphs"])
                parent_text = parent_text[:4000]
                for i, para in enumerate(art["paragraphs"], 1):
                    if not para.strip():
                        continue
                    text = para.strip()
                    chunks.append({
                        "chunk_id": f"{doc_id}_{art['article']}_{i}_{iso_date}",
                        "parent_id": f"{doc_id}_{art['article']}_{iso_date}",
                        "text": text,
                        "parent_text": parent_text,
                        "source_type": source_type,
                        "doc_id": doc_id,
                        "article": art["article"],
                        "paragraph": str(i),
                        "redaction_date": iso_date,
                        "in_force": False,
                        "url": f"{BASE_URL}/rus/docs/{doc_id}#z{art['article']}",
                        "doc_name": f"{doc_name} (ред. {archive_date})",
                        "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                    })

            print(f"  {len(raw_articles)} статей → {len(chunks)} чанков")
            all_chunks.extend(chunks)
            await asyncio.sleep(2.0)

        # Скрапим утратившие силу НП ВС — хранятся с in_force=False и явным superseded_by
        for decree in SUPERSEDED_DECREES:
            print(f"\nScraping superseded decree: {decree['name']}")
            html = await fetch_page(client, decree["url"])
            if not html:
                print(f"  SKIP — could not fetch {decree['url']}")
                await asyncio.sleep(2.0)
                continue

            raw_articles = parse_adilet_doc(html, decree)
            chunks = []
            for art in raw_articles:
                parent_text = f"Пункт {art['article']}. {art['title']}\n\n" + "\n".join(art["paragraphs"])
                parent_text = parent_text[:4000]
                for i, para in enumerate(art["paragraphs"], 1):
                    if not para.strip():
                        continue
                    text = para.strip()
                    chunks.append({
                        "chunk_id": f"{decree['doc_id']}_{art['article']}_{i}",
                        "parent_id": f"{decree['doc_id']}_{art['article']}",
                        "text": text,
                        "parent_text": parent_text,
                        "source_type": decree["source_type"],
                        "doc_id": decree["doc_id"],
                        "article": art["article"],
                        "paragraph": str(i),
                        "redaction_date": decree["redaction_date"],
                        "in_force": False,
                        "superseded_by": decree.get("superseded_by", ""),
                        "superseded_date": decree.get("superseded_date", ""),
                        "url": f"{decree['url']}#z{art['article']}",
                        "doc_name": decree["name"],
                        "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
                    })

            print(f"  {len(raw_articles)} пунктов → {len(chunks)} чанков (in_force=False)")
            all_chunks.extend(chunks)
            await asyncio.sleep(2.0)

    out = DATA_DIR / "adilet_historical.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_chunks)} historical chunks → {out}")
    return all_chunks


if __name__ == "__main__":
    asyncio.run(scrape_historical())

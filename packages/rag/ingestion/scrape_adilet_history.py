"""Scrape historical redactions of KZ laws from adilet.zan.kz.

Ingests selected snapshots (-3 years) tagged with redaction_date and in_force=False.
Current version stays in_force=True; historical allow answering "what was the law in 2022".

Selected redactions:
  ТК РК (K1500000414):
    27.06.2022, 04.07.2023, 01.01.2024

  Социальный кодекс (K2300000224):
    20.04.2023 (первая редакция), 04.07.2023, 01.01.2024
"""
import asyncio
import json
from pathlib import Path

import httpx
from packages.rag.ingestion.scrape_adilet import fetch_page, parse_adilet_doc, DOCUMENTS

DATA_DIR = Path("data/raw")
BASE_URL = "https://adilet.zan.kz"

HISTORICAL = [
    ("K1500000414", "27.06.2022", "labor_code",  1.0),
    ("K1500000414", "04.07.2023", "labor_code",  1.0),
    ("K1500000414", "01.01.2024", "labor_code",  1.0),
    ("K2300000224", "20.04.2023", "social_code", 0.95),
    ("K2300000224", "04.07.2023", "social_code", 0.95),
    ("K2300000224", "01.01.2024", "social_code", 0.95),
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

        for doc_id, archive_date, source_type, weight in HISTORICAL:
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
                "hierarchy_weight": weight,
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
                    chunks.append({
                        "chunk_id": f"{doc_id}_{art['article']}_{i}_{iso_date}",
                        "parent_id": f"{doc_id}_{art['article']}_{iso_date}",
                        "text": para.strip(),
                        "parent_text": parent_text,
                        "source_type": source_type,
                        "doc_id": doc_id,
                        "article": art["article"],
                        "paragraph": str(i),
                        "redaction_date": iso_date,
                        "in_force": False,
                        "url": f"{BASE_URL}/rus/docs/{doc_id}#z{art['article']}",
                        "hierarchy_weight": weight,
                        "doc_name": f"{doc_name} (ред. {archive_date})",
                    })

            print(f"  {len(raw_articles)} статей → {len(chunks)} чанков")
            all_chunks.extend(chunks)
            await asyncio.sleep(2.0)

    out = DATA_DIR / "adilet_historical.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_chunks)} historical chunks → {out}")
    return all_chunks


if __name__ == "__main__":
    asyncio.run(scrape_historical())

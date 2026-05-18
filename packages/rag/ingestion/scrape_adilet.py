"""Universal scraper for adilet.zan.kz — КZ official legal database."""
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from selectolax.parser import HTMLParser
from rich.console import Console
from rich.progress import track

console = Console()

BASE_URL = "https://adilet.zan.kz"
DATA_DIR = Path("data/raw")

# Known documents with their metadata
DOCUMENTS = {
    "tk_rk": {
        "doc_id": "K1500000414",
        "url": f"{BASE_URL}/rus/docs/K1500000414",
        "source_type": "labor_code",
        "name": "Трудовой кодекс РК",
        "hierarchy_weight": 1.0,
        "redaction_date": "2026-07-11",
        "in_force": True,
    },
    "social_code": {
        "doc_id": "K2300000224",
        "url": f"{BASE_URL}/rus/docs/K2300000224",
        "source_type": "social_code",
        "name": "Социальный кодекс РК",
        "hierarchy_weight": 0.95,
        "redaction_date": "2026-01-01",
        "in_force": True,
    },
    "koap_rk": {
        "doc_id": "K1400000235",
        "url": f"{BASE_URL}/rus/docs/K1400000235",
        "source_type": "koap",
        "name": "КоАП РК",
        "hierarchy_weight": 0.9,
        "redaction_date": "2026-01-01",
        "in_force": True,
        # Only labor-related articles
        "whitelist_articles": list(range(86, 100)) + [97, 414, 415, 416, 417, 418, 419, 420],
    },
    "np_vs_labor": {
        "doc_id": "P170000009S",
        "url": f"{BASE_URL}/rus/docs/P170000009S",
        "source_type": "sc_decree",
        "name": "НП ВС РК № 9 от 06.10.2017 о трудовых спорах",
        "hierarchy_weight": 0.85,
        "redaction_date": "2023-01-01",
        "in_force": True,
    },
}

# Government decrees on labor topics (sample list — add more as needed)
GOVT_DECREES = [
    {
        "doc_id": "P1200001406",
        "url": f"{BASE_URL}/rus/docs/P1200001406",
        "source_type": "government_decree",
        "name": "Правила исчисления средней заработной платы",
        "hierarchy_weight": 0.8,
        "redaction_date": "2023-01-01",
        "in_force": True,
    },
]


async def fetch_page(client: httpx.AsyncClient, url: str, retries: int = 3) -> str | None:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for attempt in range(retries):
        try:
            r = await client.get(url, timeout=30.0)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as e:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                console.print(f"[red]Failed {url}: {e}")
                return None


def parse_adilet_doc(html: str, meta: dict) -> list[dict]:
    """Extract articles and paragraphs from adilet.zan.kz document page."""
    tree = HTMLParser(html)
    articles = []
    whitelist = set(meta.get("whitelist_articles", []))

    # adilet structure: articles are in <div class="pT"> or similar containers
    # Try multiple selectors as adilet markup varies slightly between docs
    article_blocks = (
        tree.css("div.ArticleText")
        or tree.css("div.actArticle")
        or tree.css("div.docArticle")
        or tree.css("article")
    )

    if not article_blocks:
        # Fallback: extract all paragraphs under the main content area
        content = tree.css_first("div.doc-text, div.docContent, div#docContent")
        if content:
            texts = [p.text(strip=True) for p in content.css("p") if p.text(strip=True)]
            if texts:
                articles.append({
                    "article": "0",
                    "title": meta["name"],
                    "paragraphs": texts,
                })
        return articles

    for block in article_blocks:
        # Extract article number
        num_el = block.css_first(".articleNum, .artNum, span.num")
        num_text = num_el.text(strip=True) if num_el else ""
        article_num = re.sub(r"\D", "", num_text) or "0"

        # Only apply whitelist if we actually parsed a real article number
        if whitelist and article_num != "0" and int(article_num) not in whitelist:
            continue

        # Extract article title
        title_el = block.css_first(".articleTitle, .artTitle, .title")
        title = title_el.text(strip=True) if title_el else f"Статья {article_num}"

        # Extract paragraphs (пункты)
        para_texts = []
        for p in block.css("p, div.paragraph, div.p"):
            t = p.text(strip=True)
            if t and len(t) > 20:
                para_texts.append(t)

        if para_texts:
            articles.append({
                "article": article_num,
                "title": title,
                "paragraphs": para_texts,
            })

    return articles


async def scrape_document(meta: dict, client: httpx.AsyncClient) -> list[dict]:
    """Scrape a single document and return structured chunks."""
    html = await fetch_page(client, meta["url"])
    if not html:
        return []

    raw_articles = parse_adilet_doc(html, meta)
    whitelist = set(meta.get("whitelist_articles", []))
    chunks = []
    for art in raw_articles:
        # Skip fallback article "0" when whitelist is active — full-doc parent_text is too large
        if whitelist and art["article"] == "0":
            continue
        parent_text = f"Статья {art['article']}. {art['title']}\n\n" + "\n".join(art["paragraphs"])
        # Cap parent_text so single-chunk files don't bloat JSON
        parent_text = parent_text[:4000]
        for i, para in enumerate(art["paragraphs"], 1):
            if not para.strip():
                continue
            chunks.append({
                "chunk_id": f"{meta['doc_id']}_{art['article']}_{i}",
                "parent_id": f"{meta['doc_id']}_{art['article']}",
                "text": para.strip(),
                "parent_text": parent_text,
                "source_type": meta["source_type"],
                "doc_id": meta["doc_id"],
                "article": art["article"],
                "paragraph": str(i),
                "redaction_date": meta["redaction_date"],
                "in_force": meta["in_force"],
                "url": f"{meta['url']}#z{art['article']}",
                "hierarchy_weight": meta["hierarchy_weight"],
                "doc_name": meta["name"],
            })

    console.print(f"[green]✓ {meta['name']}: {len(raw_articles)} статей, {len(chunks)} чанков")
    return chunks


async def scrape_all() -> list[dict]:
    all_chunks = []
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False) as client:
        docs = list(DOCUMENTS.values()) + GOVT_DECREES
        for meta in docs:
            chunks = await scrape_document(meta, client)
            all_chunks.extend(chunks)
            # Polite rate limiting
            await asyncio.sleep(1.5)

    # Save raw
    out_path = DATA_DIR / "adilet_chunks.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    console.print(f"\n[bold green]Всего чанков: {len(all_chunks)}. Сохранено в {out_path}")
    return all_chunks


if __name__ == "__main__":
    asyncio.run(scrape_all())

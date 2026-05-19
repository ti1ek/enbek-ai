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

BLOCK_CHARS = 2000           # target size for one embedding child chunk
LARGE_ARTICLE_THRESHOLD = 4000  # articles with body > this get block-chunked

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
        "doc_id": "P240000001S",
        "url": f"{BASE_URL}/rus/docs/P240000001S",
        "source_type": "sc_decree",
        "name": "НП ВС РК № 1 от 28.11.2024 о трудовых спорах",
        "hierarchy_weight": 0.85,
        "redaction_date": "2024-11-28",
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


def _group_paragraphs_into_blocks(paragraphs: list[str], block_size: int = BLOCK_CHARS) -> list[str]:
    """Group paragraphs into blocks of approximately block_size chars."""
    blocks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current and current_len + len(para) > block_size:
            blocks.append("\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)
    if current:
        blocks.append("\n".join(current))
    return blocks


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
    """Extract articles and paragraphs from adilet.zan.kz.

    adilet uses flat HTML: articles are marked as
      <p><b><a name="zN"></a>Статья M. Title</b></p>
    followed by <p id="..."> paragraph elements.
    """
    whitelist = set(meta.get("whitelist_articles", []))

    # Split HTML into segments by article anchors
    # Pattern: <a name="zN"></a>Статья M.
    article_pattern = re.compile(
        r'<a\s+name="z\d+"></a>\s*Статья\s+(\d+[-\d]*)[\.\s]([^<]*)',
        re.IGNORECASE,
    )

    articles = []
    segments = article_pattern.split(html)
    # segments = [pre, art_num, art_title, content, art_num, art_title, content, ...]

    i = 1
    while i + 2 < len(segments):
        art_num_str = segments[i].strip()
        art_title = re.sub(r"\s+", " ", segments[i + 1].strip())
        content_html = segments[i + 2]

        # Parse article number (handle "138-2" → 138)
        art_num_int = int(re.match(r"(\d+)", art_num_str).group(1)) if re.match(r"\d", art_num_str) else 0

        i += 3

        # Apply whitelist filter
        if whitelist and art_num_int not in whitelist:
            continue

        # Extract paragraph texts from content segment
        para_tree = HTMLParser(content_html)
        para_texts = []
        for p_el in para_tree.css("p"):
            t = p_el.text(strip=True)
            # Skip empty, whitespace-only, or very short items
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 30:
                para_texts.append(t)

        if para_texts:
            articles.append({
                "article": art_num_str,
                "title": art_title or f"Статья {art_num_str}",
                "paragraphs": para_texts,
            })

    if not articles:
        # Fallback: return all paragraphs as a single block
        tree = HTMLParser(html)
        texts = [
            re.sub(r"\s+", " ", p.text(strip=True))
            for p in tree.css("p")
            if len(p.text(strip=True)) > 30
        ]
        if texts:
            articles.append({
                "article": "0",
                "title": meta["name"],
                "paragraphs": texts,
            })

    return articles


async def scrape_document(
    meta: dict,
    client: httpx.AsyncClient,
    archive_url: str | None = None,
    redaction_date_override: str | None = None,
    in_force_override: bool | None = None,
) -> list[dict]:
    """Scrape a single document and return structured chunks.

    archive_url: if set, fetch this URL instead of meta["url"] (for historical versions)
    redaction_date_override: overrides meta["redaction_date"] (for historical versions)
    in_force_override: overrides meta["in_force"] (historical → False)
    """
    url = archive_url or meta["url"]
    html = await fetch_page(client, url)
    if not html:
        return []

    raw_articles = parse_adilet_doc(html, meta)
    whitelist = set(meta.get("whitelist_articles", []))
    redaction_date = redaction_date_override or meta["redaction_date"]
    in_force = in_force_override if in_force_override is not None else meta["in_force"]

    chunks = []
    for art in raw_articles:
        if whitelist and art["article"] == "0":
            continue
        # parent_text = full article text; no truncation — LLM handles long context
        parent_text = f"Статья {art['article']}. {art['title']}\n\n" + "\n".join(art["paragraphs"])
        article_body = "\n".join(art["paragraphs"])
        suffix = f"_{redaction_date}" if in_force_override is False else ""

        if len(article_body) > LARGE_ARTICLE_THRESHOLD:
            # Large article: group paragraphs into semantic blocks for better embedding
            blocks = _group_paragraphs_into_blocks(art["paragraphs"])
            for i, block in enumerate(blocks, 1):
                chunks.append({
                    "chunk_id": f"{meta['doc_id']}_{art['article']}_b{i}{suffix}",
                    "parent_id": f"{meta['doc_id']}_{art['article']}{suffix}",
                    "text": block,
                    "parent_text": parent_text,
                    "source_type": meta["source_type"],
                    "doc_id": meta["doc_id"],
                    "article": art["article"],
                    "paragraph": f"block_{i}",
                    "redaction_date": redaction_date,
                    "in_force": in_force,
                    "url": f"{meta['url']}#z{art['article']}",
                    "hierarchy_weight": meta["hierarchy_weight"],
                    "doc_name": meta["name"],
                })
        else:
            # Small article: one child per paragraph (fine-grained similarity)
            for i, para in enumerate(art["paragraphs"], 1):
                if not para.strip():
                    continue
                chunks.append({
                    "chunk_id": f"{meta['doc_id']}_{art['article']}_{i}{suffix}",
                    "parent_id": f"{meta['doc_id']}_{art['article']}{suffix}",
                    "text": para.strip(),
                    "parent_text": parent_text,
                    "source_type": meta["source_type"],
                    "doc_id": meta["doc_id"],
                    "article": art["article"],
                    "paragraph": str(i),
                    "redaction_date": redaction_date,
                    "in_force": in_force,
                    "url": f"{meta['url']}#z{art['article']}",
                    "hierarchy_weight": meta["hierarchy_weight"],
                    "doc_name": meta["name"],
                })

    label = f"{meta['name']} @ {redaction_date}" if redaction_date_override else meta["name"]
    console.print(f"[green]✓ {label}: {len(raw_articles)} статей, {len(chunks)} чанков")
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

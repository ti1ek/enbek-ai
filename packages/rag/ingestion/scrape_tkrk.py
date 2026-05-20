"""Scraper for tkrk.kz — ТК РК articles with expert commentary.

Strategy:
  1. Start at /chast-1/razdel-1/glava-1/statya-1
  2. Follow .nav-next a links until the end of the code
  3. For each page split .post-content at first <h2>:
       - before h2  → official article text  (skipped — already in adilet)
       - after  h2  → commentary chunk(s)
  4. One chunk per commentary block (each <h2> = separate block)
"""
import asyncio
import hashlib
import json
import re
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser
from rich.console import Console

console = Console()
DATA_DIR = Path("data/chunks")
BASE = "https://tkrk.kz"
START_URL = f"{BASE}/chast-1/razdel-1/glava-1/statya-1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
}


async def fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, timeout=20.0)
        r.raise_for_status()
        return r.text
    except Exception as e:
        console.print(f"[red]  Error {url}: {e}")
        return None


def _article_num(title: str) -> str:
    m = re.search(r"Статья\s+(\d+[-\d]*)", title, re.IGNORECASE)
    return m.group(1) if m else ""


def parse_article_page(html: str, url: str) -> dict | None:
    """Extract article number, official text, commentary blocks, and next URL."""
    tree = HTMLParser(html)

    title_el = tree.css_first(".entry-title, .fusion-post-title")
    if not title_el:
        return None
    title = title_el.text(strip=True)
    article_num = _article_num(title)
    if not article_num:
        return None

    content_el = tree.css_first(".post-content")
    if not content_el:
        return None

    # Split children at h2 boundaries
    # Before first h2 → article text; each h2+following paragraphs → one commentary block
    commentary_blocks: list[dict] = []
    current_heading = ""
    current_paras: list[str] = []
    in_commentary = False

    for node in content_el.iter():
        tag = getattr(node, "tag", None)
        if tag == "h2":
            # Save previous commentary block
            if in_commentary and current_paras:
                commentary_blocks.append({
                    "heading": current_heading,
                    "text": " ".join(current_paras),
                })
            current_heading = re.sub(r"\s+", " ", node.text(strip=True))
            current_paras = []
            in_commentary = True
        elif tag == "p" and in_commentary:
            t = re.sub(r"\s+", " ", node.text(strip=True))
            if len(t) > 30:
                current_paras.append(t)

    if in_commentary and current_paras:
        commentary_blocks.append({
            "heading": current_heading,
            "text": " ".join(current_paras),
        })

    # Next article link
    next_el = tree.css_first(".nav-next a")
    next_url = next_el.attributes.get("href") if next_el else None

    return {
        "article": article_num,
        "title": title,
        "url": url,
        "commentary_blocks": commentary_blocks,
        "next_url": next_url,
    }


def build_chunks(page: dict) -> list[dict]:
    chunks = []
    art = page["article"]
    url = page["url"]
    title = page["title"]

    for i, block in enumerate(page["commentary_blocks"], 1):
        heading = block["heading"]
        body = block["text"]
        if not body.strip():
            continue

        # Include heading in text so it's searchable
        text = f"{heading}\n\n{body}" if heading else body
        parent_text = f"{title}\n\n{text}"[:4000]

        chunks.append({
            "chunk_id": f"tkrk_{art}_{i}",
            "parent_id": f"tkrk_{art}",
            "text": text,
            "parent_text": parent_text,
            "source_type": "labor_code_commentary",
            "doc_id": "tkrk_commentary",
            "article": art,
            "paragraph": str(i),
            "redaction_date": "",
            "in_force": True,
            "url": url,
            "doc_name": "Комментарий к ТК РК (tkrk.kz)",
            "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "commented_doc_id": "K1500000414",
        })

    return chunks


async def _collect_urls(client: httpx.AsyncClient) -> list[str]:
    """Fetch all article URLs from sitemap, sorted by article number."""
    import re as _re
    html = await fetch(client, f"{BASE}/post-sitemap1.xml")
    if not html:
        return [START_URL]
    urls = _re.findall(r'<loc>(https://tkrk\.kz/[^<]+)</loc>', html)
    statya_urls = [u for u in urls if "statya-" in u]

    def _art_num(u: str) -> int:
        m = _re.search(r"statya-(\d+)", u)
        return int(m.group(1)) if m else 0

    return sorted(statya_urls, key=_art_num)


async def scrape_tkrk() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_chunks: list[dict] = []
    articles_scraped = 0
    errors = 0

    import urllib3
    urllib3.disable_warnings()

    console.print(f"\n[bold blue]Scraping tkrk.kz commentary via sitemap")

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
        urls = await _collect_urls(client)
        console.print(f"  Найдено {len(urls)} статей в sitemap")

        for url in urls:
            html = await fetch(client, url)
            if not html:
                errors += 1
                continue

            page = parse_article_page(html, url)
            if not page:
                errors += 1
                continue

            chunks = build_chunks(page)
            all_chunks.extend(chunks)
            articles_scraped += 1

            if articles_scraped % 50 == 0:
                console.print(
                    f"  Статья {page['article']}: "
                    f"{len(chunks)} чанков  |  всего {len(all_chunks)}"
                )

            await asyncio.sleep(0.4)

    console.print(
        f"\n[bold green]tkrk.kz: {articles_scraped} статей, "
        f"{len(all_chunks)} чанков комментариев, {errors} ошибок"
    )

    out = DATA_DIR / "tkrk_commentary.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    console.print(f"[green]Сохранено → {out}")
    return all_chunks


if __name__ == "__main__":
    asyncio.run(scrape_tkrk())

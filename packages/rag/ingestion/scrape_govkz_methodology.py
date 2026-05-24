"""Scraper for methodology documents from gov.kz using Playwright + LlamaParse.

Documents:
  1. Методические рекомендации по разработке системы оплаты труда
     https://www.gov.kz/memleket/entities/enbek/documents/details/272701?lang=ru
  2. Методические рекомендации по применению Единых правил исчисления СЗП
     https://www.gov.kz/memleket/entities/enbek/documents/details/3208?lang=ru

Flow:
  Playwright renders SPA → find PDF download link → httpx download →
  LlamaParse → markdown → chunk by section headings
"""
import asyncio
import hashlib
import json
import re
import tempfile
import os
from pathlib import Path

import httpx
from rich.console import Console

console = Console()
DATA_DIR = Path("data/chunks")

METHODOLOGY_DOCS = [
    {
        "doc_id": "govkz_272701",
        "name": "Методические рекомендации по разработке системы оплаты труда",
        "url": "https://www.gov.kz/memleket/entities/enbek/documents/details/272701?lang=ru",
        "source_type": "mintrud_guidelines",
    },
    {
        "doc_id": "govkz_3208",
        "name": "Методические рекомендации по применению Единых правил исчисления среднезаработной платы",
        "url": "https://www.gov.kz/memleket/entities/enbek/documents/details/3208?lang=ru",
        "source_type": "mintrud_guidelines",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
}

MIN_CHUNK_LEN = 80



async def _get_file_url_via_playwright(page_url: str) -> tuple[str | None, str | None]:
    """Use Playwright to intercept the gov.kz API response and extract file path."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print("[red]Playwright not installed: uv run playwright install chromium")
        return None, None

    # Extract document ID from URL
    m = re.search(r"/details/(\d+)", page_url)
    if not m:
        return None, None
    doc_id = m.group(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(ignore_https_errors=True, locale="ru-RU")
        page = await ctx.new_page()

        doc_data: dict = {}

        async def on_response(resp):
            if f"content-manager/documents/{doc_id}" in resp.url and "view-count" not in resp.url:
                try:
                    doc_data.update(await resp.json())
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            await page.goto(page_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)
        finally:
            await browser.close()

    if not doc_data:
        return None, None

    # Extract file path from full_text list
    full_text = doc_data.get("full_text", [])
    if not full_text:
        return None, None

    doc_path = full_text[0].get("document", "")
    if not doc_path:
        return None, None

    file_url = f"https://www.gov.kz{doc_path}" if doc_path.startswith("/") else doc_path
    return file_url, None


async def _download_file(url: str) -> bytes | None:
    """Download file bytes from URL."""
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
        try:
            r = await client.get(url, timeout=60.0)
            r.raise_for_status()
            return r.content
        except Exception as e:
            console.print(f"[red]  Download failed {url}: {e}")
            return None


async def _parse_with_llamaparse(file_bytes: bytes, filename: str) -> str:
    """Parse file bytes with LlamaParse async, return markdown text."""
    import tempfile, os
    from pathlib import Path
    from packages.config import settings

    suffix = Path(filename).suffix.lower() or ".docx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        from llama_cloud_services import LlamaParse
        parser = LlamaParse(
            api_key=settings.llama_cloud_api_key,
            result_type="markdown",
            verbose=False,
        )
        docs = await parser.aload_data(tmp_path)
        text = "\n\n".join(d.text for d in docs if d.text)
        return text.strip()
    except Exception as e:
        console.print(f"[red]  LlamaParse error: {e}")
        return ""
    finally:
        os.unlink(tmp_path)


def _chunk_markdown(text: str, meta: dict) -> list[dict]:
    """Split markdown document into chunks by heading sections."""
    chunks = []

    # Split on H1/H2/H3 headings
    heading_re = re.compile(r'^(#{1,3})\s+(.+)$', re.MULTILINE)
    sections: list[tuple[int, str, str]] = []  # (level, title, body)

    last_end = 0
    preamble = ""
    matches = list(heading_re.finditer(text))

    if not matches:
        # No headings — chunk by paragraphs (~500 chars each)
        paras = [p.strip() for p in re.split(r'\n{2,}', text) if len(p.strip()) >= MIN_CHUNK_LEN]
        for i, para in enumerate(paras, 1):
            chunks.append(_make_chunk(meta, para, str(i), "", i))
        return chunks

    # Text before first heading
    preamble = text[:matches[0].start()].strip()

    for idx, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        sections.append((level, title, body))

    if preamble:
        sections.insert(0, (1, meta["name"], preamble))

    for sec_idx, (level, title, body) in enumerate(sections, 1):
        # If section is long, split into paragraphs
        paras = [p.strip() for p in re.split(r'\n{2,}', body) if len(p.strip()) >= MIN_CHUNK_LEN]
        if not paras and len(body) >= MIN_CHUNK_LEN:
            paras = [body]

        # parent_text = section heading + full body
        parent_text = f"{title}\n\n{body}"[:4000]

        if not paras:
            continue

        if len(body) <= 1200:
            # Short section: one chunk
            text_block = f"{title}\n\n{body}" if title else body
            chunks.append(_make_chunk(meta, text_block, str(sec_idx), title, sec_idx, parent_text))
        else:
            # Long section: one chunk per paragraph
            for para_idx, para in enumerate(paras, 1):
                text_block = f"{title}\n\n{para}" if title else para
                chunks.append(_make_chunk(
                    meta, text_block, f"{sec_idx}_{para_idx}", title, sec_idx, parent_text
                ))

    return chunks


def _make_chunk(
    meta: dict,
    text: str,
    paragraph: str,
    article: str,
    sec_idx: int,
    parent_text: str | None = None,
) -> dict:
    return {
        "chunk_id": f"{meta['doc_id']}_{paragraph}",
        "parent_id": f"{meta['doc_id']}_{sec_idx}",
        "text": text,
        "parent_text": parent_text or text,
        "source_type": meta["source_type"],
        "doc_id": meta["doc_id"],
        "article": article,
        "paragraph": paragraph,
        "redaction_date": meta.get("redaction_date", ""),
        "in_force": True,
        "url": meta["url"],
        "doc_name": meta["name"],
        "content_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
    }


async def scrape_methodology_doc(meta: dict) -> list[dict]:
    """Scrape one methodology document. Returns list of chunks."""
    console.print(f"\n[bold blue]Scraping: {meta['name']}")
    console.print(f"  URL: {meta['url']}")

    file_url, html = await _get_file_url_via_playwright(meta["url"])

    if not file_url:
        console.print("[yellow]  No file URL found via Playwright — trying direct HTML text extraction")
        if html:
            return _extract_chunks_from_html(html, meta)
        console.print("[red]  Failed to get content")
        return []

    console.print(f"  File URL: {file_url}")
    file_bytes = await _download_file(file_url)
    if not file_bytes:
        return []

    ext = file_url.split("/")[-1].split("?")[0].rsplit(".", 1)[-1] or "pdf"
    filename = f"{meta['doc_id']}.{ext}"
    console.print(f"  Downloaded {len(file_bytes):,} bytes ({filename})")

    # Save raw file for re-processing without re-downloading
    raw_path = DATA_DIR / filename
    raw_path.write_bytes(file_bytes)
    console.print(f"  Saved raw file → {raw_path}")

    markdown = await _parse_with_llamaparse(file_bytes, filename)
    if not markdown.strip():
        console.print("[red]  LlamaParse returned empty text")
        return []

    console.print(f"  LlamaParse: {len(markdown):,} chars of markdown")

    chunks = _chunk_markdown(markdown, meta)
    console.print(f"[green]  → {len(chunks)} chunks")
    return chunks


def _extract_chunks_from_html(html: str, meta: dict) -> list[dict]:
    """Fallback: extract text from rendered HTML if no file found."""
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html)
    # Remove nav/header/footer noise
    for sel in ["nav", "header", "footer", ".menu", ".breadcrumb", "script", "style"]:
        for el in tree.css(sel):
            el.decompose()

    text = re.sub(r'\s+', ' ', tree.body.text(strip=True)).strip() if tree.body else ""
    if len(text) < 100:
        return []

    return _chunk_markdown(text, meta)


async def scrape_all_methodology() -> list[dict]:
    import urllib3
    urllib3.disable_warnings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict] = []
    for meta in METHODOLOGY_DOCS:
        chunks = await scrape_methodology_doc(meta)
        all_chunks.extend(chunks)
        await asyncio.sleep(2.0)

    out = DATA_DIR / "govkz_methodology.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    console.print(f"\n[bold green]Методические рекомендации: {len(all_chunks)} чанков → {out}")
    return all_chunks


if __name__ == "__main__":
    asyncio.run(scrape_all_methodology())

"""Scraper for Q&A from enbek.gov.kz — Ministry of Labour RK FAQ."""
import asyncio
import json
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser
from rich.console import Console

console = Console()
DATA_DIR = Path("data/raw")
BASE = "https://enbek.gov.kz"
FAQ_URL = f"{BASE}/ru/faq"


async def fetch(client: httpx.AsyncClient, url: str) -> str | None:
    import urllib3; urllib3.disable_warnings()
    try:
        r = await client.get(url, timeout=20.0)
        r.raise_for_status()
        return r.text
    except Exception as e:
        console.print(f"[red]Error fetching {url}: {e}")
        return None


def parse_faq_page(html: str) -> list[dict]:
    tree = HTMLParser(html)
    pairs = []

    # Try common FAQ accordion selectors
    for item in tree.css(".faq-item, .accordion-item, .qa-item, details, .question-answer"):
        q_el = item.css_first("summary, .question, h3, .faq-question, dt")
        a_el = item.css_first(".answer, .faq-answer, p, dd, .content")
        if q_el and a_el:
            q = q_el.text(strip=True)
            a = a_el.text(strip=True)
            if q and a and len(a) > 20:
                pairs.append({"question": q, "answer": a})

    # Fallback: look for dl/dt/dd pattern
    if not pairs:
        for dl in tree.css("dl"):
            dts = dl.css("dt")
            dds = dl.css("dd")
            for dt, dd in zip(dts, dds):
                q = dt.text(strip=True)
                a = dd.text(strip=True)
                if q and a:
                    pairs.append({"question": q, "answer": a})

    return pairs


async def scrape_faq() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    all_qa = []
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, verify=False) as client:
        # Try fetching multiple pages
        for page in range(1, 6):
            url = f"{FAQ_URL}?page={page}" if page > 1 else FAQ_URL
            html = await fetch(client, url)
            if not html:
                break
            pairs = parse_faq_page(html)
            if not pairs:
                console.print(f"[yellow]Страница {page}: 0 Q&A — возможно SPA, нужен Playwright")
                break
            all_qa.extend(pairs)
            console.print(f"[green]Страница {page}: {len(pairs)} Q&A")
            await asyncio.sleep(1.0)

    # If no results — enbek.gov.kz might be SPA
    if not all_qa:
        console.print("[yellow]Static scraping не дал результатов. Пробуем Playwright...")
        all_qa = await scrape_faq_playwright()

    # Convert to chunks format
    chunks = []
    for i, qa in enumerate(all_qa):
        chunks.append({
            "chunk_id": f"mintrud_faq_{i}",
            "parent_id": f"mintrud_faq_{i}",
            "text": f"Вопрос: {qa['question']}\nОтвет: {qa['answer']}",
            "parent_text": f"Вопрос: {qa['question']}\nОтвет: {qa['answer']}",
            "source_type": "mintrud_faq",
            "doc_id": "mintrud_faq",
            "article": "",
            "paragraph": "",
            "redaction_date": "",
            "in_force": True,
            "url": FAQ_URL,
            "hierarchy_weight": 0.5,
            "doc_name": "Q&A Министерства труда РК",
        })

    out = DATA_DIR / "mintrud_faq.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    console.print(f"[bold green]Q&A Минтруда: {len(chunks)} записей → {out}")
    return chunks


async def scrape_faq_playwright() -> list[dict]:
    """Fallback: use Playwright for SPA pages."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        console.print("[red]Playwright не установлен. Запустите: uv run playwright install chromium")
        return []

    pairs = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        await page.goto(FAQ_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.wait_for_timeout(2000)

        # Scroll to load lazy content
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(500)

        # Extract Q&A
        items = await page.query_selector_all(".faq-item, .accordion-item, details, .qa-item")
        for item in items:
            q_el = await item.query_selector("summary, .question, h3, dt")
            a_el = await item.query_selector(".answer, p, dd")
            if q_el and a_el:
                q = (await q_el.inner_text()).strip()
                a = (await a_el.inner_text()).strip()
                if q and a:
                    pairs.append({"question": q, "answer": a})

        await browser.close()
        console.print(f"[green]Playwright: {len(pairs)} Q&A найдено")
    return pairs


if __name__ == "__main__":
    asyncio.run(scrape_faq())

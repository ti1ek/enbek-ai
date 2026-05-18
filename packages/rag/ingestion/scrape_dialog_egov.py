"""Scraper for Q&A from dialog.egov.kz — official KZ government dialogue portal.

Scrapes Ministry of Labor officials' blogs:
- /blogs/2719746  — Министерство труда и социальной защиты (текущий)
- /blogs/2654212  — Актаева Лязат Мейрашевна
- /blogs/32777    — Министерство труда и социальной защиты (основной)
"""
import asyncio
import json
import re
from pathlib import Path

import httpx
from selectolax.parser import HTMLParser
from rich.console import Console

console = Console()
DATA_DIR = Path("data/raw")
BASE = "https://dialog.egov.kz"

# Blogs to scrape — (blog_id, official_name, max_pages)
BLOGS = [
    ("32777",   "Министерство труда и социальной защиты РК", 30),
    ("2719746", "Министерство труда — Жұманбаев Е.Т.",       20),
    ("2654212", "Актаева Лязат Мейрашевна",                   20),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,kk;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        r = await client.get(url, timeout=20.0)
        r.raise_for_status()
        return r.text
    except Exception as e:
        console.print(f"[red]Error {url}: {e}")
        return None


def _clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_page(html: str) -> list[dict]:
    """Extract Q&A pairs from one listing page.

    Structure on each page:
      <div class="row" ...>
        <ul class="blog-info">... № 765824 ...</ul>
        <p> QUESTION TEXT </p>
        <a class="readmore" href="/blogs/all-questions/765824">Толығырақ</a>
        <button onclick="showAnswers(1, 765824)">Жауаптар</button>
      </div>
      <div class="row answers" id="765824" style="display:none">
        <p> ANSWER TEXT </p>
        <span class="answer-info">Автор  01.01.2025</span>
      </div>
    """
    tree = HTMLParser(html)
    pairs = []

    # Build answer map: id → answer text
    answer_map: dict[str, str] = {}
    for ans_div in tree.css("div.answers"):
        qid = ans_div.attributes.get("id", "").strip()
        if not qid:
            continue
        # Remove the "Жауаптар" header and answer-info spans
        for tag in ans_div.css("h4, span.answer-info"):
            tag.decompose()
        ans_text = _clean(ans_div.html or "")
        # Remove div wrapper noise
        ans_text = re.sub(r"</?div[^>]*>", " ", ans_text)
        ans_text = _clean(ans_text)
        if len(ans_text) > 30:
            answer_map[qid] = ans_text

    if not answer_map:
        return []

    # For each readmore link, find question text from surrounding context
    # Pattern: <p>QUESTION...</p> ... <a class="readmore" href="/blogs/all-questions/QID">
    q_pattern = re.compile(
        r"<p>([\s\S]{50,5000}?)</p>\s*(?:<a[^>]+>\s*</a>\s*)?<a\s+class=\"readmore\"\s+href=\"/blogs/all-questions/(\d+)\"",
        re.DOTALL,
    )
    for m in q_pattern.finditer(html):
        raw_q = m.group(1)
        qid = m.group(2)
        q_text = _clean(raw_q)
        # Remove trailing ellipsis artifact
        q_text = q_text.rstrip(". ").rstrip("…").strip()
        if not q_text or len(q_text) < 20:
            continue
        ans_text = answer_map.get(qid)
        if not ans_text:
            continue
        pairs.append({
            "question_id": qid,
            "question": q_text,
            "answer": ans_text,
        })

    return pairs


async def scrape_blog(
    blog_id: str, official_name: str, max_pages: int, client: httpx.AsyncClient
) -> list[dict]:
    """Scrape all pages of one blog."""
    all_pairs = []
    seen_ids: set[str] = set()

    for page in range(1, max_pages + 1):
        url = f"{BASE}/blogs/{blog_id}/questions?page={page}"
        html = await fetch(client, url)
        if not html:
            break

        pairs = parse_page(html)
        if not pairs:
            console.print(f"  [yellow]Blog {blog_id} page {page}: 0 Q&A — stopping")
            break

        new_pairs = [p for p in pairs if p["question_id"] not in seen_ids]
        if not new_pairs:
            console.print(f"  [yellow]Blog {blog_id} page {page}: all duplicates — stopping")
            break

        for p in new_pairs:
            seen_ids.add(p["question_id"])
        all_pairs.extend(new_pairs)
        console.print(f"  [green]Blog {blog_id} page {page}: {len(new_pairs)} Q&A (total {len(all_pairs)})")
        await asyncio.sleep(1.0)

    return all_pairs


async def scrape_dialog_egov() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_qa: list[dict] = []

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
        import urllib3
        urllib3.disable_warnings()

        for blog_id, official_name, max_pages in BLOGS:
            console.print(f"\n[bold blue]Scraping blog {blog_id}: {official_name}")
            pairs = await scrape_blog(blog_id, official_name, max_pages, client)
            for p in pairs:
                p["source_blog"] = blog_id
                p["official"] = official_name
            all_qa.extend(pairs)
            console.print(f"  [bold]Blog {blog_id}: {len(pairs)} pairs total")

    # Deduplicate by question text
    seen_qs: set[str] = set()
    unique_qa = []
    for item in all_qa:
        key = item["question"][:100]
        if key not in seen_qs:
            seen_qs.add(key)
            unique_qa.append(item)

    console.print(f"\n[bold green]Total unique Q&A: {len(unique_qa)}")

    # Convert to chunk format
    chunks = []
    for i, qa in enumerate(unique_qa):
        url = f"{BASE}/blogs/all-questions/{qa['question_id']}"
        text = f"Вопрос: {qa['question']}\nОтвет Министерства труда РК: {qa['answer']}"
        chunks.append({
            "chunk_id": f"dialog_egov_{qa['question_id']}",
            "parent_id": f"dialog_egov_{qa['question_id']}",
            "text": text,
            "parent_text": text,
            "source_type": "mintrud_dialog",
            "doc_id": f"dialog_blog_{qa['source_blog']}",
            "article": "",
            "paragraph": "",
            "redaction_date": "",
            "in_force": True,
            "url": url,
            "hierarchy_weight": 0.6,
            "doc_name": f"Открытый диалог — {qa['official']}",
        })

    out = DATA_DIR / "dialog_egov_qa.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    console.print(f"[bold green]Saved {len(chunks)} chunks → {out}")
    return chunks


if __name__ == "__main__":
    asyncio.run(scrape_dialog_egov())

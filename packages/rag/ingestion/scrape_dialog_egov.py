"""Scraper for Q&A from dialog.egov.kz — official KZ government dialogue portal.

Strategy:
  1. Paginate listing at /blogs/all-questions?categoryBlogFilter=2&answeredFilter=yes
  2. Collect question IDs from each listing page (href=/blogs/all-questions/{id})
  3. Fetch each individual question page for full Q+A + metadata
     — question: div.b-question (longest Russian text, skip Kazakh nav sidebar)
     — answer:   div.blog-item (responder name + date + answer body)
  4. Filter to labor-law-relevant pairs only
  5. 1 chunk per Q+A pair (question and answer combined, never split)
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

LISTING_URL = f"{BASE}/blogs/all-questions"
LISTING_PARAMS = {
    "categoryBlogFilter": "2",  # labor / social category
    "answeredFilter": "yes",
}

MAX_PAGES = 400  # ~10 questions per page; adjust if site has fewer

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,kk;q=0.8",
}

LABOR_KEYWORDS = [
    "трудов", "работник", "работодател", "договор", "увольн", "отпуск",
    "зарплат", "оклад", "ТК РК", "статья", "кодекс", "пособи",
    "больничн", "декрет", "испытательн", "дисциплинар", "взыскани",
    "компенсаци", "сверхурочн", "командиров", "сокращени", "пенси",
    "социальн", "страховани", "прогул", "нарушени", "охрана труда",
    "трудоустрой", "занятост", "безработ", "пенсионн",
]


def _is_labor_relevant(text: str) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in LABOR_KEYWORDS)


async def fetch(client: httpx.AsyncClient, url: str, params: dict | None = None) -> str | None:
    try:
        r = await client.get(url, params=params, timeout=25.0)
        r.raise_for_status()
        return r.text
    except Exception as e:
        console.print(f"[red]  Error {url}: {e}")
        return None


async def collect_ids_from_listing(client: httpx.AsyncClient) -> list[str]:
    """Paginate listing and collect all question IDs."""
    ids: list[str] = []
    seen: set[str] = set()

    for page in range(1, MAX_PAGES + 1):
        params = {**LISTING_PARAMS, "page": str(page)}
        html = await fetch(client, LISTING_URL, params=params)
        if not html:
            break

        page_ids = re.findall(r'href="/blogs/all-questions/(\d+)"', html)
        new_ids = [qid for qid in page_ids if qid not in seen]
        if not new_ids:
            console.print(f"  Page {page}: no new IDs — stopping")
            break

        seen.update(new_ids)
        ids.extend(new_ids)
        console.print(f"  Page {page}: +{len(new_ids)} IDs (total {len(ids)})")
        await asyncio.sleep(0.5)

    return ids


def _extract_responder_and_date(raw: str) -> tuple[str, str]:
    """Extract responder name and answer date from the first line of blog-item text."""
    m = re.match(
        r"^([А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z\s\.\-]{2,60}?)(\d{2}\.\d{2}\.\d{4})",
        raw.strip(),
    )
    if m:
        return m.group(1).strip().rstrip(" .,"), m.group(2)
    return "", ""


async def fetch_question_page(qid: str, client: httpx.AsyncClient) -> dict | None:
    """Fetch individual question page, extract full Q+A with metadata."""
    url = f"{BASE}/blogs/all-questions/{qid}"
    html = await fetch(client, url)
    if not html:
        return None

    tree = HTMLParser(html)

    # ── Question: longest Russian-language div.b-question (skip Kazakh nav) ──
    bqs = tree.css("div.b-question")
    question_text = ""
    candidates = [(bq.text(strip=True), bq) for bq in bqs]
    for t, _ in sorted(candidates, key=lambda x: -len(x[0])):
        if len(t) > 100 and re.search(r"[а-яёА-ЯЁ]{3,}\s+[а-яёА-ЯЁ]{3,}", t):
            if not re.search(r"Жазбалар|Өмірбаян|Өтініш|Мұрағат", t):
                question_text = re.sub(r"\s+", " ", t).strip()
                break
    if not question_text:
        return None

    # ── Previous question context (referenced earlier question, if any) ───────
    prev_question = ""
    for sel in ("div.b-question-prev", ".prev-question", ".related-question"):
        prev_el = tree.css_first(sel)
        if prev_el:
            prev_question = re.sub(r"\s+", " ", prev_el.text(strip=True))
            break

    # ── Answer: div.blog-item ─────────────────────────────────────────────────
    blog_item = tree.css_first("div.blog-item")
    if not blog_item:
        return None

    answer_raw = blog_item.text(strip=True)
    # Strip Angular template artifact "blog?.question?.answers (N)"
    answer_raw = re.sub(r"blog\?\.question\?\.answers\s*\(\d+\)", "", answer_raw).strip()

    responder_name, answer_date = _extract_responder_and_date(answer_raw)

    # Remove the responder name + date prefix from answer body
    answer_body = re.sub(
        r"^[А-ЯЁа-яёA-Za-z][А-ЯЁа-яёA-Za-z\s\.\-]{2,60}?\d{2}\.\d{2}\.\d{4},?\s*\d{2}:\d{2}",
        "",
        answer_raw,
    ).strip()
    answer_text = re.sub(r"\s+", " ", answer_body).strip()

    if len(answer_text) < 50:
        return None
    if not _is_labor_relevant(question_text + " " + answer_text):
        return None

    return {
        "question_id": qid,
        "question": question_text,
        "answer": answer_text,
        "responder": responder_name,
        "answer_date": answer_date,
        "prev_question": prev_question,
        "url": url,
    }


async def scrape_dialog_egov() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Собираем ID вопросов с {LISTING_URL} (categoryBlogFilter=2, answeredFilter=yes)...")

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, verify=False) as client:
        import urllib3
        urllib3.disable_warnings()

        ids = await collect_ids_from_listing(client)
        console.print(f"  Всего ID: {len(ids)}")

        sem = asyncio.Semaphore(5)
        pairs: list[dict] = []
        errors = 0

        async def fetch_one(qid: str) -> dict | None:
            async with sem:
                result = await fetch_question_page(qid, client)
                await asyncio.sleep(0.3)
                return result

        tasks = [fetch_one(qid) for qid in ids]
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            if result:
                pairs.append(result)
            else:
                errors += 1
            if (i + 1) % 100 == 0:
                console.print(
                    f"  Progress: {i+1}/{len(ids)}, "
                    f"found {len(pairs)} labor Q&A, skipped {errors}"
                )

    # Deduplicate by question prefix
    seen_qs: set[str] = set()
    unique_qa: list[dict] = []
    for item in pairs:
        key = item["question"][:80].lower()
        if key not in seen_qs:
            seen_qs.add(key)
            unique_qa.append(item)

    console.print(f"\n[bold green]Уникальных Q&A: {len(unique_qa)}")

    # Build chunks — 1 chunk = full question + full answer (never split)
    chunks: list[dict] = []
    for qa in unique_qa:
        lines: list[str] = []
        if qa.get("prev_question"):
            lines.append(f"Предыдущий вопрос: {qa['prev_question']}")
        lines.append(f"Вопрос: {qa['question']}")
        responder_label = qa["responder"] if qa.get("responder") else "Министерство труда РК"
        lines.append(f"Ответ ({responder_label}): {qa['answer']}")
        text = "\n".join(lines)

        chunks.append({
            "chunk_id": f"dialog_egov_{qa['question_id']}",
            "parent_id": f"dialog_egov_{qa['question_id']}",
            "text": text,
            "parent_text": text,
            "source_type": "mintrud_dialog",
            "doc_id": "dialog_egov",
            "article": "",
            "paragraph": "",
            "redaction_date": qa.get("answer_date", ""),
            "in_force": True,
            "url": qa["url"],
            "hierarchy_weight": 0.6,
            "doc_name": "Открытый диалог — Министерство труда РК",
            "responder": qa.get("responder", ""),
            "question_id": qa["question_id"],
        })

    out = DATA_DIR / "dialog_egov_qa.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    console.print(f"[bold green]Сохранено {len(chunks)} чанков → {out}")
    return chunks


if __name__ == "__main__":
    asyncio.run(scrape_dialog_egov())

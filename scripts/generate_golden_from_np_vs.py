"""Generate golden Q&A examples from НП ВС chunks — single batch request.

Sends all substantive НП ВС paragraphs to Gemini in one call.
Run:
    uv run python scripts/generate_golden_from_np_vs.py
"""
import json
import re
from openai import OpenAI
from packages.config import settings
from packages.rag.qdrant_client import get_qdrant

ACTIVE_DOC_ID = "P240000001S"

SKIP_PREFIXES = ["Информационно-правовая", "Министерство Юстиции", "Сноска", "2)пункт"]

CATEGORY_KEYWORDS = {
    "увольнение": ["расторжен", "прекращен", "уволен", "восстановлен"],
    "трудовой договор": ["трудовой договор", "заключен", "срок договора", "испытан"],
    "дисциплина": ["дисциплинарн", "взыскание", "проступок", "прогул"],
    "материальная ответственность": ["материальн", "ущерб", "возмещен"],
    "согласительная комиссия": ["согласительн", "комиссия", "спор"],
    "профсоюз": ["профсоюз"],
    "оплата труда": ["заработн", "оплат"],
    "отпуск": ["отпуск"],
}

BATCH_PROMPT = """Ты — эксперт по трудовому праву Казахстана.

Ниже перечислены параграфы из Нормативного постановления Верховного Суда РК о трудовых спорах (НП ВС № 1 от 28.11.2024). Каждый пронумерован [N].

Для каждого параграфа:
1. Составь 1-2 конкретных вопроса, которые мог бы задать работник или HR-специалист (как на юридическом форуме)
2. Выдели 3-4 ключевых слова/фразы из параграфа, которые должны быть в правильном ответе

{chunks_text}

Верни JSON-массив без пояснений:
[
  {{"id": 1, "questions": ["вопрос 1", "вопрос 2"], "keywords": ["слово 1", "слово 2", "слово 3"]}},
  {{"id": 2, "questions": ["вопрос"], "keywords": ["слово 1", "слово 2"]}},
  ...
]"""


def _detect_category(text: str) -> str:
    t = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return cat
    return "трудовой спор"


def _extract_articles(text: str) -> list[str]:
    arts = []
    for m in re.findall(r"стать[ея][хмию]?\s+(\d+[\-\d]*)", text, re.IGNORECASE):
        if m not in arts and int(re.sub(r"\D.*", "", m)) < 300:
            arts.append(m)
    return arts[:4]


def _parse_json(raw: str):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def main() -> None:
    client = get_qdrant()
    llm = OpenAI(api_key=settings.effective_llm_api_key, base_url=settings.llm_api_base)

    golden_path = "data/golden/qa.jsonl"
    existing = [json.loads(l) for l in open(golden_path) if l.strip()]
    next_id = max(int(e["id"][1:]) for e in existing) + 1
    print(f"Existing: {len(existing)}, next id: q{next_id:03d}")

    chunks_raw, _ = client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter={"must": [{"key": "doc_id", "match": {"value": ACTIVE_DOC_ID}}]},
        limit=100, with_payload=True,
    )

    def _sort_key(r):
        m = re.search(r"\d+", str(r.payload.get("paragraph", "")))
        return int(m.group()) if m else 0

    chunks = sorted(chunks_raw, key=_sort_key)

    # Filter substantive chunks
    good = []
    for r in chunks:
        p = r.payload or {}
        text = p.get("text", "").strip()
        if len(text) < 100:
            continue
        if any(text.startswith(s) for s in SKIP_PREFIXES):
            continue
        good.append({"para": p.get("paragraph", ""), "text": text, "payload": p})

    print(f"Substantive chunks: {len(good)}")

    # Build numbered text for prompt
    numbered = "\n\n".join(f"[{i+1}] {c['text'][:700]}" for i, c in enumerate(good))

    print("Sending batch request to Gemini...")
    resp = llm.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": BATCH_PROMPT.format(chunks_text=numbered)}],
        temperature=0.3,
        max_tokens=5000,
    )
    raw = resp.choices[0].message.content or "[]"
    results = _parse_json(raw)
    print(f"Got {len(results)} results from LLM")

    new_examples = []
    for item in results:
        idx = item.get("id", 0) - 1
        if idx < 0 or idx >= len(good):
            continue
        chunk = good[idx]
        questions = item.get("questions") or []
        keywords = item.get("keywords") or []
        articles = _extract_articles(chunk["text"])
        category = _detect_category(chunk["text"])

        for q in questions[:2]:
            if not q or len(q) < 10:
                continue
            para = chunk["para"]
            new_examples.append({
                "id": f"q{next_id:03d}",
                "question": q,
                "expected_articles": articles,
                "expected_answer_keywords": keywords,
                "category": category,
                "source": f"НП ВС РК № 1 от 28.11.2024 {para}",
            })
            print(f"  q{next_id:03d}: {q[:80]}")
            next_id += 1

    print(f"\nGenerated {len(new_examples)} new examples")
    if new_examples:
        with open(golden_path, "a") as f:
            for ex in new_examples:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"Total: {len(existing) + len(new_examples)} examples in {golden_path}")


if __name__ == "__main__":
    main()

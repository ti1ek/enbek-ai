"""Metadata enrichment for Qdrant chunks.

enrich(chunk)          — adds doc_type, year, chunk_type (deterministic, no LLM)
tag_topics_llm(chunks) — adds topic list via GPT-4.1-mini (async, batched)

Called at ingest time in scripts/ingest.py.
"""
import asyncio
import json
import re

# ── doc_type ──────────────────────────────────────────────────────────────────

_DOC_TYPE: dict[str, str] = {
    "labor_code": "code",
    "social_code": "code",
    "koap": "code",
    "civil_code": "code",
    "sc_decree": "court_decree",
    "government_decree": "decree",
    "ministerial_order": "order",
    "law": "law",
    "mintrud_dialog": "qa",
    "mintrud_faq": "qa",
    "mintrud_guidelines": "guideline",
    "labor_code_commentary": "commentary",
}

_QA_SOURCES = {"mintrud_dialog", "mintrud_faq"}
_GUIDELINE_SOURCES = {"mintrud_guidelines"}
_COMMENTARY_SOURCES = {"labor_code_commentary"}

# ── Canonical topic taxonomy (used in LLM prompt) ─────────────────────────────

TOPICS: list[str] = [
    "отпуск",
    "увольнение",
    "рабочее_время",
    "зарплата",
    "трудовой_договор",
    "охрана_труда",
    "декрет_материнство",
    "дисциплина",
    "командировка",
    "пенсия",
    "социальное_страхование",
    "занятость",
    "компенсация",
    "профсоюз",
    "иностранные_работники",
    "материальная_ответственность",
    "трудовые_споры",
    "электронный_документооборот",
    "системы_оплаты_труда",
    "делопроизводство",
]

_TOPICS_STR = ", ".join(TOPICS)

_SYSTEM_PROMPT = f"""Ты — классификатор текстов по трудовому праву Казахстана.
Для каждого текста выбери подходящие темы из списка (0 или несколько):
{_TOPICS_STR}

Правила:
- Выбирай только темы, о которых текст реально говорит
- Если текст не относится ни к одной теме — верни пустой список
- Отвечай строго JSON-массивом массивов, по одному массиву на каждый текст
- Пример ответа для 3 текстов: [["отпуск"], ["зарплата", "трудовой_договор"], []]"""


def enrich(chunk: dict) -> dict:
    """Add doc_type, year, chunk_type to a chunk (in-place + return). No LLM."""
    st = chunk.get("source_type", "")

    chunk["doc_type"] = _DOC_TYPE.get(st, "other")

    rd = chunk.get("redaction_date", "") or ""
    chunk["year"] = int(rd[:4]) if rd and rd[:4].isdigit() else None

    if st in _QA_SOURCES:
        chunk["chunk_type"] = "qa"
    elif st in _GUIDELINE_SOURCES:
        chunk["chunk_type"] = "guideline"
    elif st in _COMMENTARY_SOURCES:
        chunk["chunk_type"] = "commentary"
    else:
        chunk["chunk_type"] = "article"

    return chunk


async def tag_topics_llm(
    chunks: list[dict],
    batch_size: int = 20,
    concurrency: int = 8,
) -> None:
    """Tag all chunks with topics using GPT-4.1-mini. Modifies chunks in-place.

    batch_size: texts per API call (20 keeps prompts short, reduces per-call cost)
    concurrency: parallel API calls
    """
    from openai import AsyncOpenAI
    from packages.config import settings
    from rich.progress import track

    client = AsyncOpenAI(
        api_key=settings.effective_llm_api_key,
        base_url=settings.llm_api_base,
    )
    sem = asyncio.Semaphore(concurrency)

    async def tag_batch(batch: list[dict]) -> None:
        texts = [
            (c.get("text") or "")[:600]  # truncate to keep tokens low
            for c in batch
        ]
        numbered = "\n\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))

        async with sem:
            try:
                resp = await client.chat.completions.create(
                    model=settings.llm_mini_model,
                    temperature=0.0,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": numbered},
                    ],
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or "[]"
                # Model returns {"topics": [[...], [...]]} or just [[...], [...]]
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    parsed = next(iter(parsed.values()), [])
                if not isinstance(parsed, list) or len(parsed) != len(batch):
                    parsed = [[] for _ in batch]
            except Exception as e:
                # Fallback: empty topics for the batch
                parsed = [[] for _ in batch]
                from rich.console import Console
                Console().print(f"[yellow]  LLM topic batch error: {e}")

        for chunk, topics in zip(batch, parsed):
            if isinstance(topics, list):
                # Filter to only known topics to avoid hallucinations
                chunk["topic"] = [t for t in topics if t in set(TOPICS)]
            else:
                chunk["topic"] = []

    # Build batches
    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]

    tasks = [tag_batch(b) for b in batches]

    # Run with progress bar
    from rich.console import Console
    console = Console()
    console.print(f"  LLM topic tagging: {len(chunks)} чанков / {len(batches)} батчей")

    completed = 0
    for coro in asyncio.as_completed(tasks):
        await coro
        completed += 1
        if completed % 10 == 0 or completed == len(batches):
            console.print(f"  [{completed}/{len(batches)}] батчей обработано")

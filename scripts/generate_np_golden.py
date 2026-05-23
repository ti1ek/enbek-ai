"""Generate 25 golden Q&A pairs from НП ВС РК №1/2024 chunks with reference answers."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from packages.config import settings
from packages.llm import chat_complete
from rich.console import Console

console = Console()
OUT_FILE = Path("data/golden/np_golden.jsonl")
TARGET = 25
NP_DOC = "НП ВС РК № 1 от 28.11.2024 о трудовых спорах"


def fetch_np_chunks() -> list[dict]:
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    results, _ = client.scroll(
        settings.qdrant_collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="sc_decree")),
        ]),
        limit=300,
        with_payload=True,
        with_vectors=False,
    )
    chunks = []
    for r in results:
        p = r.payload
        if NP_DOC not in p.get("doc_name", ""):
            continue
        text = p.get("text", "").strip()
        if len(text) > 100:
            chunks.append({"id": str(r.id), "text": text, "url": p.get("url", "")})
    return chunks


SYSTEM = """Ты эксперт по трудовому праву Казахстана. На основе предоставленного фрагмента НП ВС РК №1/2024 сгенерируй вопрос и эталонный ответ.

Правила:
- Вопрос должен быть конкретным, практическим (как спросил бы HR или работник)
- Ответ — точное разъяснение из фрагмента, без додумывания
- Ответ должен быть полным, 2-5 предложений
- Если фрагмент не содержит конкретного правила — верни null

Ответ строго в JSON:
{"question": "...", "answer": "...", "category": "..."}
или {"question": null} если фрагмент не подходит"""


def generate_qa(chunk: dict) -> dict | None:
    prompt = f"Фрагмент НП ВС РК №1/2024:\n\n{chunk['text']}"
    try:
        r = chat_complete(
            model=settings.llm_mini_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=500,
        )
        raw = r.choices[0].message.content.strip()
        # strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        if not data.get("question"):
            return None
        return {
            "question": data["question"],
            "reference_answer": data["answer"],
            "category": data.get("category", "нп_вс"),
            "source_text": chunk["text"],
            "url": chunk["url"],
        }
    except Exception as e:
        console.print(f"  [yellow]Skip chunk: {e}")
        return None


def main():
    console.print(f"[bold blue]Fetching НП ВС РК №1/2024 chunks...")
    chunks = fetch_np_chunks()
    console.print(f"Found {len(chunks)} chunks")

    results = []
    for i, chunk in enumerate(chunks):
        if len(results) >= TARGET:
            break
        console.print(f"  [{i+1}/{len(chunks)}] generating... ({len(results)}/{TARGET} done)")
        qa = generate_qa(chunk)
        if qa:
            qa["id"] = f"np{len(results)+1:03d}"
            results.append(qa)
            console.print(f"  [green]✓ {qa['question'][:70]}")
        time.sleep(0.3)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    console.print(f"\n[bold green]Saved {len(results)} golden examples → {OUT_FILE}")


if __name__ == "__main__":
    main()

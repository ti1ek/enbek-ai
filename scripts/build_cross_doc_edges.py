"""Build cross-document knowledge graph edges.

For each labor_code/social_code article that involves calculations or payments,
finds which specific chunks in ministerial_order/government_decree/sc_decree
implement or detail that article.

Two-step LLM matching (gpt-4.1-mini):
  Step 1: article × document  → yes/no (is doc relevant to this article?)
  Step 2: article × doc chunks → which specific paragraphs?

Output: data/chunks/cross_doc_edges.json
Idempotent: re-run overwrites. Does NOT modify Qdrant.
"""
import json
import time
from pathlib import Path

from openai import OpenAI
from qdrant_client import QdrantClient, models

from packages.config import settings

OUTPUT = Path("data/chunks/cross_doc_edges.json")
COLLECTION = settings.qdrant_collection

# Keywords that indicate an article involves calculation or payment
_CALC_KEYWORDS = [
    "средняя", "компенсац", "выплачивает", "в порядке", "исчисля",
    "пособи", "выходное", "средний заработок", "оплачивает",
]

# Source types to search for regulatory docs
_REG_SOURCE_TYPES = ["ministerial_order", "government_decree", "sc_decree"]

# Source types for code articles
_CODE_SOURCE_TYPES = ["labor_code", "social_code"]


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def get_llm() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


def _scroll_all(client: QdrantClient, filt: models.Filter, fields: list[str]) -> list:
    results = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=filt,
            limit=512,
            offset=offset,
            with_payload=fields,
            with_vectors=False,
        )
        results.extend(batch)
        if offset is None:
            break
    return results


def get_code_articles(client: QdrantClient) -> list[dict]:
    """Get representative chunk per article for labor_code/social_code.

    Only articles whose text contains calculation/payment keywords.
    Returns list of {doc_id, article, text, source_type}.
    """
    points = _scroll_all(
        client,
        models.Filter(must=[
            models.FieldCondition(
                key="source_type",
                match=models.MatchAny(any=_CODE_SOURCE_TYPES),
            ),
            models.FieldCondition(key="in_force", match=models.MatchValue(value=True)),
        ]),
        fields=["doc_id", "article", "source_type", "text", "parent_text"],
    )

    # Group by (doc_id, article), keep longest text chunk
    by_art: dict[tuple, dict] = {}
    for p in points:
        pl = p.payload or {}
        art = pl.get("article", "")
        if not art or art == "0":
            continue
        text = pl.get("parent_text") or pl.get("text") or ""
        if not any(kw in text.lower() for kw in _CALC_KEYWORDS):
            continue
        key = (pl.get("doc_id", ""), art)
        if key not in by_art or len(text) > len(by_art[key]["text"]):
            by_art[key] = {
                "doc_id": pl.get("doc_id", ""),
                "article": art,
                "source_type": pl.get("source_type", ""),
                "text": text[:800],
            }

    articles = sorted(by_art.values(), key=lambda x: (x["doc_id"], int(x["article"].split("-")[0]) if x["article"].split("-")[0].isdigit() else 999))
    print(f"Code articles with calculation keywords: {len(articles)}")
    return articles


def get_regulatory_docs(client: QdrantClient) -> list[dict]:
    """Get all in-force regulatory docs with all their chunks.

    Returns list of {doc_id, doc_name, source_type, chunks: [{chunk_id, paragraph, text}]}.
    """
    points = _scroll_all(
        client,
        models.Filter(must=[
            models.FieldCondition(
                key="source_type",
                match=models.MatchAny(any=_REG_SOURCE_TYPES),
            ),
            models.FieldCondition(key="in_force", match=models.MatchValue(value=True)),
        ]),
        fields=["doc_id", "doc_name", "source_type", "paragraph", "text"],
    )

    docs: dict[str, dict] = {}
    for p in points:
        pl = p.payload or {}
        doc_id = pl.get("doc_id", "")
        if not doc_id:
            continue
        if doc_id not in docs:
            docs[doc_id] = {
                "doc_id": doc_id,
                "doc_name": pl.get("doc_name", doc_id),
                "source_type": pl.get("source_type", ""),
                "chunks": [],
            }
        text = (pl.get("text") or "").strip()
        if text and len(text) > 50:
            docs[doc_id]["chunks"].append({
                "chunk_id": str(p.id),
                "paragraph": pl.get("paragraph", ""),
                "text": text[:400],
            })

    result = list(docs.values())
    print(f"Regulatory docs: {len(result)}")
    for d in result:
        print(f"  {d['doc_id']} ({d['source_type']}): {len(d['chunks'])} chunks — {d['doc_name'][:60]}")
    return result


def step1_is_doc_linked(article: dict, doc: dict, llm: OpenAI) -> tuple[bool, str]:
    """Ask LLM: does this regulatory doc implement or detail this code article?"""
    doc_summary = "\n".join(
        f"[{c['paragraph']}] {c['text'][:200]}"
        for c in doc["chunks"][:5]
    )
    prompt = (
        f"Статья кодекса (ст.{article['article']} {article['source_type']}):\n"
        f"{article['text'][:600]}\n\n"
        f"Подзаконный акт ({doc['doc_name'][:80]}):\n"
        f"{doc_summary}\n\n"
        "Этот подзаконный акт содержит конкретный порядок расчёта, методику или детализацию "
        "применения нормы из этой статьи кодекса?\n\n"
        'Верни JSON: {"linked": true или false, "reason": "одно предложение или пусто если false"}'
    )
    try:
        resp = llm.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return bool(data.get("linked")), data.get("reason", "")
    except Exception as e:
        print(f"    step1 error: {e}")
        return False, ""


def step2_find_paragraphs(article: dict, doc: dict, llm: OpenAI) -> list[dict]:
    """Ask LLM: which specific chunks of this doc are relevant to this article?"""
    chunks_text = "\n\n".join(
        f"[{i+1}] paragraph={c['paragraph']}\n{c['text'][:300]}"
        for i, c in enumerate(doc["chunks"])
    )
    prompt = (
        f"Статья кодекса (ст.{article['article']} {article['source_type']}):\n"
        f"{article['text'][:500]}\n\n"
        f"Пункты подзаконного акта:\n{chunks_text}\n\n"
        "Укажи номера пунктов (из списка выше) которые содержат порядок расчёта или "
        "детализацию применительно к этой статье кодекса. "
        "Только те пункты где есть конкретная норма или формула — не вводные и не подписи.\n\n"
        'Верни JSON: {"relevant": [1, 3, ...], "reason": "одно предложение"}'
    )
    try:
        resp = llm.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        indices = [i - 1 for i in (data.get("relevant") or []) if isinstance(i, int)]
        reason = data.get("reason", "")
        result = []
        for idx in indices:
            if 0 <= idx < len(doc["chunks"]):
                c = doc["chunks"][idx]
                result.append({
                    "target_chunk_id": c["chunk_id"],
                    "target_paragraph": c["paragraph"],
                    "reason": reason,
                })
        return result
    except Exception as e:
        print(f"    step2 error: {e}")
        return []


def main() -> None:
    client = get_qdrant()
    llm = get_llm()

    articles = get_code_articles(client)
    reg_docs = get_regulatory_docs(client)

    edges: list[dict] = []
    total_pairs = len(articles) * len(reg_docs)
    done = 0

    print(f"\nStep 1: checking {total_pairs} article×doc pairs...")

    for article in articles:
        for doc in reg_docs:
            done += 1
            linked, reason = step1_is_doc_linked(article, doc, llm)
            if linked:
                print(f"  ✓ ст.{article['article']} → {doc['doc_id']} | {reason[:80]}")
                paragraphs = step2_find_paragraphs(article, doc, llm)
                for para in paragraphs:
                    edges.append({
                        "source_doc_id": article["doc_id"],
                        "source_article": article["article"],
                        "source_type": article["source_type"],
                        "target_doc_id": doc["doc_id"],
                        "target_chunk_id": para["target_chunk_id"],
                        "target_paragraph": para["target_paragraph"],
                        "reason": para["reason"],
                    })
            # Avoid rate limits
            time.sleep(0.05)

        if done % (len(reg_docs) * 5) == 0:
            print(f"  Progress: {done}/{total_pairs} pairs, {len(edges)} edges found")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(edges, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone. {len(edges)} cross-doc edges → {OUTPUT}")
    by_art: dict[str, int] = {}
    for e in edges:
        k = f"ст.{e['source_article']}"
        by_art[k] = by_art.get(k, 0) + 1
    for art, cnt in sorted(by_art.items(), key=lambda x: -x[1])[:20]:
        print(f"  {art}: {cnt} edges")


if __name__ == "__main__":
    main()

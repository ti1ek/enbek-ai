"""Evaluation runner for Enbek AI RAG pipelines.

Metrics:
  - hit@5: expected article in top-5 retrieved sources
  - faithfulness: LLM-as-judge (GPT-4.1-mini) — no hallucinations
  - relevance: LLM-as-judge (1-5 scale)
  - chain_match: fraction of expected_chain items found in sources/answer in order (multi-hop only)
  - wrong_conclusion: LLM-as-judge — 1 if final conclusion contradicts chain (multi-hop only)
  - latency_ms, cost_usd: deterministic
"""
import json
import time
import uuid
from pathlib import Path

from openai import OpenAI
from rich.console import Console
from rich.table import Table

from packages.config import settings

console = Console()
GOLDEN_FILE = Path("data/golden/qa.jsonl")
RESULTS_DIR = Path("data/evals")


def load_golden() -> list[dict]:
    items = []
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def compute_hit_at_5(sources: list[dict], expected_articles: list[str]) -> bool:
    """Check if any expected article appears in top-5 sources."""
    if not expected_articles or expected_articles == ["0"]:
        return True  # No specific article expected → always pass
    retrieved_arts = {str(s.get("article", "")) for s in sources[:5]}
    return bool(set(expected_articles) & retrieved_arts)


def _chain_item_matches_source(item: dict, source: dict) -> bool:
    """Does an expected_chain item match a single retrieved source?"""
    dt = item["doc_type"]
    aop = str(item["article_or_point"])
    src_type = source.get("source_type", "")
    src_art = str(source.get("article", ""))
    src_para = str(source.get("paragraph", ""))
    src_url = source.get("url", "")
    if dt != src_type:
        return False
    if aop.isdigit():
        return src_art == aop or aop in src_url
    if aop.lower().startswith("п."):
        point_num = aop.split(".")[-1].strip()
        # Regulations (приказы/постановления) store the point number inside the
        # chunk text/paragraph as "block_N", not as a clean point field — so for
        # these doc types a same-type source counts as a context match.
        if dt in {"ministerial_order", "government_decree"}:
            return True
        return (
            src_para == point_num
            or f"п.{point_num}" in src_url.lower()
            or f"point-{point_num}" in src_url.lower()
            or f"p{point_num}" in src_url.lower()
        )
    # topical / freeform article_or_point — match by doc_type only
    return True


def compute_chain_match(sources: list[dict], answer: str, expected_chain: list[dict]) -> float:
    """Fraction of expected_chain items satisfied in the correct order.

    For each item:
      - if must_appear_in_context: a source matching (doc_type, article_or_point)
        must be found at or after the current scan position in `sources` (order check).
      - if must_appear_in_answer: the article/point token must appear in the answer text.
    """
    if not expected_chain:
        return 1.0
    matched = 0
    src_idx = 0
    answer_lower = (answer or "").lower()
    for item in expected_chain:
        ctx_required = bool(item.get("must_appear_in_context", False))
        ans_required = bool(item.get("must_appear_in_answer", False))
        aop = str(item["article_or_point"]).lower()

        ctx_ok = not ctx_required
        new_src_idx = src_idx
        if ctx_required:
            for i in range(src_idx, len(sources)):
                if _chain_item_matches_source(item, sources[i]):
                    ctx_ok = True
                    new_src_idx = i + 1
                    break

        ans_ok = True
        if ans_required:
            tokens = [aop]
            if aop.startswith("п."):
                tokens.append(aop.replace("п.", "пункт"))
                tokens.append(aop.replace("п.", "п. "))
            ans_ok = any(t in answer_lower for t in tokens)

        if ctx_ok and ans_ok:
            matched += 1
            src_idx = new_src_idx
    return matched / len(expected_chain)


def compute_keyword_match(answer: str, keywords: list[str]) -> float:
    """Fraction of keywords found in answer (case-insensitive)."""
    if not keywords or keywords == ["out_of_scope"]:
        # out_of_scope: check that answer is short and doesn't cite articles
        return 1.0 if len(answer) < 300 else 0.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / len(keywords)


_llm_judge: OpenAI | None = None


def get_judge():
    global _llm_judge
    if _llm_judge is None:
        _llm_judge = OpenAI(api_key=settings.openai_api_key)
    return _llm_judge


def judge_faithfulness(question: str, context: str, answer: str) -> float:
    """LLM-as-judge: 0.0 (hallucination) to 1.0 (faithful)."""
    prompt = f"""Проверь, содержит ли ответ утверждения, не подтверждённые предоставленным контекстом.

Вопрос: {question}
Контекст (извлечённые статьи закона): {context[:1500]}
Ответ: {answer[:800]}

Ответь ТОЛЬКО числом от 0.0 до 1.0, где:
- 1.0 = все утверждения подтверждены контекстом
- 0.5 = частично подтверждено
- 0.0 = содержит утверждения без основания в контексте

Число:"""
    try:
        r = get_judge().chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        val = float(r.choices[0].message.content.strip())
        return max(0.0, min(1.0, val))
    except Exception:
        return 0.5


def judge_wrong_conclusion(question: str, expected_chain: list[dict], answer: str,
                            expected_conclusion: str | None = None) -> int:
    """LLM-as-judge: 1 if final conclusion contradicts the expected chain, 0 if consistent."""
    chain_desc = "\n".join(
        f"- {item.get('doc_type', '?')} {item.get('article_or_point', '?')}"
        for item in expected_chain
    )
    expected_block = f"\nОжидаемый итоговый вывод: {expected_conclusion}\n" if expected_conclusion else ""
    prompt = f"""Проверь, соответствует ли итоговый вывод ответа правильной цепочке норм права.

Вопрос: {question}

Ожидаемая цепочка норм (в правильном порядке применения):
{chain_desc}
{expected_block}
Ответ модели:
{(answer or "")[:1500]}

Ответь ТОЛЬКО одной цифрой 0 или 1:
- 0 = итоговый вывод ответа верный и соответствует ожидаемой цепочке
- 1 = итоговый вывод неверный, противоречит цепочке или упускает ключевую норму, меняющую вывод

Цифра:"""
    try:
        r = get_judge().chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=5,
        )
        raw = r.choices[0].message.content.strip()
        return 1 if raw and raw[0] == "1" else 0
    except Exception:
        return 0


def judge_relevance(question: str, answer: str) -> float:
    """LLM-as-judge: relevance 1-5, normalized to 0-1."""
    prompt = f"""Оцени насколько ответ отвечает на вопрос по шкале 1-5:
1 = совсем не отвечает
3 = частично отвечает
5 = полностью и точно отвечает

Вопрос: {question}
Ответ: {answer[:600]}

Ответь ТОЛЬКО числом 1, 2, 3, 4 или 5:"""
    try:
        r = get_judge().chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=5,
        )
        val = float(r.choices[0].message.content.strip())
        return (val - 1) / 4  # normalize to 0-1
    except Exception:
        return 0.5


def run_pipeline(question: str, pipeline: str) -> dict:
    """Run the specified pipeline and return result."""
    t0 = time.perf_counter()
    if pipeline == "basic":
        from packages.rag.basic_rag import basic_rag
        result = basic_rag(question)
        context = ""  # basic_rag doesn't return context
    else:
        from apps.api.graph import run_graph
        graph_result = run_graph(question, pipeline=pipeline)
        result = {
            "answer": graph_result["answer"],
            "sources": graph_result["sources"],
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "cost_usd": 0.0,
            "pipeline": pipeline,
        }
        context = ""

    return result


def run_evals(pipeline: str = "advanced", max_judge_calls: int = 30,
              only_multi_hop: bool = False, tag: str | None = None) -> dict:
    """Run evaluation on golden dataset.

    Args:
        pipeline: "basic" or "advanced"
        max_judge_calls: Limit LLM judge calls to control cost
        only_multi_hop: If True, run only items with `multi_hop: true`
        tag: Optional prefix override for output files (e.g. "baseline_multihop")

    Returns:
        Summary dict with all metrics.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    golden = load_golden()
    if only_multi_hop:
        golden = [g for g in golden if g.get("multi_hop")]
    console.print(f"\n[bold blue]Running evals: pipeline={pipeline}, n={len(golden)} examples"
                  + (" [multi-hop only]" if only_multi_hop else ""))

    results = []
    judge_calls = 0

    for i, item in enumerate(golden):
        qid = item["id"]
        question = item["question"]
        expected_articles = item.get("expected_articles", [])
        keywords = item.get("expected_answer_keywords", [])
        category = item.get("category", "unknown")
        expected_chain = item.get("expected_chain") or []
        expected_conclusion = item.get("expected_conclusion")
        is_multi_hop = bool(item.get("multi_hop"))

        console.print(f"  [{i+1}/{len(golden)}] {qid}: {question[:60]}...")

        try:
            result = run_pipeline(question, pipeline)
            answer = result["answer"]
            sources = result["sources"]
            latency_ms = result.get("latency_ms", 0)
            cost_usd = result.get("cost_usd", 0.0)

            hit5 = compute_hit_at_5(sources, expected_articles)
            kw_match = compute_keyword_match(answer, keywords)

            chain_match = None
            if is_multi_hop and expected_chain:
                chain_match = round(compute_chain_match(sources, answer, expected_chain), 3)

            # LLM judge (limited calls to control cost)
            faithfulness = relevance = wrong_conclusion = None
            if judge_calls < max_judge_calls:
                context_str = " | ".join(
                    s.get("url", "") + " ст." + str(s.get("article", "")) for s in sources[:3]
                )
                faithfulness = judge_faithfulness(question, context_str, answer)
                relevance = judge_relevance(question, answer)
                judge_calls += 2
                if is_multi_hop and expected_chain and judge_calls < max_judge_calls:
                    wrong_conclusion = judge_wrong_conclusion(
                        question, expected_chain, answer, expected_conclusion
                    )
                    judge_calls += 1

            record = {
                "id": qid,
                "question": question,
                "category": category,
                "pipeline": pipeline,
                "multi_hop": is_multi_hop,
                "answer": answer,
                "sources": sources,
                "hit_at_5": hit5,
                "keyword_match": round(kw_match, 3),
                "chain_match": chain_match,
                "faithfulness": faithfulness,
                "relevance": relevance,
                "wrong_conclusion": wrong_conclusion,
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
            }
            results.append(record)

        except Exception as e:
            console.print(f"  [red]Error on {qid}: {e}")
            results.append({"id": qid, "error": str(e), "pipeline": pipeline})

        time.sleep(0.5)  # rate limiting

    # Compute summary
    valid = [r for r in results if "error" not in r]
    n = len(valid)
    mh_valid = [r for r in valid if r.get("multi_hop")]
    mh_with_chain = [r for r in mh_valid if r.get("chain_match") is not None]
    mh_with_wc = [r for r in mh_valid if r.get("wrong_conclusion") is not None]
    summary = {
        "pipeline": pipeline,
        "n_examples": n,
        "n_multi_hop": len(mh_valid),
        "hit_at_5": round(sum(r["hit_at_5"] for r in valid) / n, 3) if n else 0,
        "keyword_match": round(sum(r["keyword_match"] for r in valid) / n, 3) if n else 0,
        "chain_match": round(
            sum(r["chain_match"] for r in mh_with_chain) / len(mh_with_chain), 3
        ) if mh_with_chain else None,
        "wrong_conclusion_rate": round(
            sum(r["wrong_conclusion"] for r in mh_with_wc) / len(mh_with_wc), 3
        ) if mh_with_wc else None,
        "faithfulness": round(
            sum(r["faithfulness"] for r in valid if r["faithfulness"] is not None) /
            max(1, sum(1 for r in valid if r["faithfulness"] is not None)), 3
        ),
        "relevance": round(
            sum(r["relevance"] for r in valid if r["relevance"] is not None) /
            max(1, sum(1 for r in valid if r["relevance"] is not None)), 3
        ),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in valid) / n) if n else 0,
        "total_cost_usd": round(sum(r["cost_usd"] for r in valid), 4),
    }

    # Print table
    table = Table(title=f"Eval Results — {pipeline.upper()}")
    for col in ["Metric", "Value"]:
        table.add_column(col)
    for k, v in summary.items():
        table.add_row(str(k), str(v))
    console.print(table)

    # Save results
    run_id = str(uuid.uuid4())[:8]
    prefix = tag if tag else pipeline
    out = RESULTS_DIR / f"{prefix}_{run_id}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary_out = RESULTS_DIR / f"{prefix}_{run_id}_summary.json"
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    console.print(f"[bold green]Results saved: {out}")
    return summary

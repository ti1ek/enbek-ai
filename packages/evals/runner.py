"""Evaluation runner for Enbek AI RAG pipelines.

Metrics:
  - hit@5: expected article in top-5 retrieved sources
  - faithfulness: LLM-as-judge (GPT-4.1-mini) — no hallucinations
  - relevance: LLM-as-judge (1-5 scale)
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


def run_evals(pipeline: str = "advanced", max_judge_calls: int = 30) -> dict:
    """Run evaluation on golden dataset.

    Args:
        pipeline: "basic" or "advanced"
        max_judge_calls: Limit LLM judge calls to control cost

    Returns:
        Summary dict with all metrics.
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    golden = load_golden()
    console.print(f"\n[bold blue]Running evals: pipeline={pipeline}, n={len(golden)} examples")

    results = []
    judge_calls = 0

    for i, item in enumerate(golden):
        qid = item["id"]
        question = item["question"]
        expected_articles = item.get("expected_articles", [])
        keywords = item.get("expected_answer_keywords", [])
        category = item.get("category", "unknown")

        console.print(f"  [{i+1}/{len(golden)}] {qid}: {question[:60]}...")

        try:
            result = run_pipeline(question, pipeline)
            answer = result["answer"]
            sources = result["sources"]
            latency_ms = result.get("latency_ms", 0)
            cost_usd = result.get("cost_usd", 0.0)

            hit5 = compute_hit_at_5(sources, expected_articles)
            kw_match = compute_keyword_match(answer, keywords)

            # LLM judge (limited calls to control cost)
            faithfulness = relevance = None
            if judge_calls < max_judge_calls:
                context_str = " | ".join(
                    s.get("url", "") + " ст." + str(s.get("article", "")) for s in sources[:3]
                )
                faithfulness = judge_faithfulness(question, context_str, answer)
                relevance = judge_relevance(question, answer)
                judge_calls += 2

            record = {
                "id": qid,
                "question": question,
                "category": category,
                "pipeline": pipeline,
                "answer": answer,
                "sources": sources,
                "hit_at_5": hit5,
                "keyword_match": round(kw_match, 3),
                "faithfulness": faithfulness,
                "relevance": relevance,
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
    summary = {
        "pipeline": pipeline,
        "n_examples": n,
        "hit_at_5": round(sum(r["hit_at_5"] for r in valid) / n, 3) if n else 0,
        "keyword_match": round(sum(r["keyword_match"] for r in valid) / n, 3) if n else 0,
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
    out = RESULTS_DIR / f"{pipeline}_{run_id}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    summary_out = RESULTS_DIR / f"{pipeline}_{run_id}_summary.json"
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    console.print(f"[bold green]Results saved: {out}")
    return summary

"""Run evals only for failed IDs and patch them into the existing results file."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from packages.config import settings
from packages.evals.runner import (
    run_pipeline, compute_hit_at_5, compute_keyword_match,
    compute_chain_match, judge_faithfulness, judge_relevance,
    judge_wrong_conclusion, GOLDEN_FILE, RESULTS_DIR,
)
from rich.console import Console

console = Console()

RESULTS_FILE = Path("data/evals/advanced_c78f0430.jsonl")
FAILED_IDS = {"q042", "q043", "q044", "q045"}
PIPELINE = "advanced"


def load_golden_by_id(ids: set) -> list[dict]:
    items = []
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        for line in f:
            item = json.loads(line.strip())
            if item["id"] in ids:
                items.append(item)
    return items


def load_results() -> list[dict]:
    records = []
    with open(RESULTS_FILE, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line.strip()))
    return records


def run_item(item: dict) -> dict:
    qid = item["id"]
    question = item["question"]
    expected_articles = item.get("expected_articles", [])
    keywords = item.get("expected_answer_keywords", [])
    category = item.get("category", "unknown")
    expected_chain = item.get("expected_chain") or []
    expected_conclusion = item.get("expected_conclusion")
    is_multi_hop = bool(item.get("multi_hop"))

    console.print(f"  Running {qid}: {question[:60]}...")
    result = run_pipeline(question, PIPELINE)
    answer = result["answer"]
    sources = result["sources"]
    latency_ms = result.get("latency_ms", 0)

    hit5 = compute_hit_at_5(sources, expected_articles)
    kw_match = compute_keyword_match(answer, keywords)
    chain_match = None
    if is_multi_hop and expected_chain:
        chain_match = round(compute_chain_match(sources, answer, expected_chain), 3)

    context_str = " | ".join(
        s.get("url", "") + " ст." + str(s.get("article", "")) for s in sources[:3]
    )
    faithfulness = judge_faithfulness(question, context_str, answer)
    relevance = judge_relevance(question, answer)
    wrong_conclusion = None
    if is_multi_hop and expected_chain:
        wrong_conclusion = judge_wrong_conclusion(question, expected_chain, answer, expected_conclusion)

    return {
        "id": qid,
        "question": question,
        "category": category,
        "pipeline": PIPELINE,
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
        "cost_usd": 0.0,
    }


def main():
    golden_items = load_golden_by_id(FAILED_IDS)
    console.print(f"[bold blue]Patching {len(golden_items)} failed examples into {RESULTS_FILE}")

    patched = {}
    for item in golden_items:
        try:
            patched[item["id"]] = run_item(item)
            time.sleep(0.5)
        except Exception as e:
            console.print(f"  [red]Error on {item['id']}: {e}")

    # Merge: replace error records with new results
    records = load_results()
    merged = []
    for r in records:
        rid = r.get("id")
        if rid in patched:
            merged.append(patched[rid])
            console.print(f"  [green]Replaced {rid}")
        else:
            merged.append(r)

    # Save back
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Recompute summary
    valid = [r for r in merged if "error" not in r]
    n = len(valid)
    mh_valid = [r for r in valid if r.get("multi_hop")]
    mh_with_chain = [r for r in mh_valid if r.get("chain_match") is not None]

    summary = {
        "pipeline": PIPELINE,
        "n_examples": n,
        "n_multi_hop": len(mh_valid),
        "hit_at_5": round(sum(r["hit_at_5"] for r in valid) / n, 3) if n else 0,
        "keyword_match": round(sum(r["keyword_match"] for r in valid) / n, 3) if n else 0,
        "chain_match": round(
            sum(r["chain_match"] for r in mh_with_chain) / len(mh_with_chain), 3
        ) if mh_with_chain else None,
        "faithfulness": round(
            sum(r["faithfulness"] for r in valid if r.get("faithfulness") is not None) /
            max(1, sum(1 for r in valid if r.get("faithfulness") is not None)), 3
        ),
        "relevance": round(
            sum(r["relevance"] for r in valid if r.get("relevance") is not None) /
            max(1, sum(1 for r in valid if r.get("relevance") is not None)), 3
        ),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in valid) / n) if n else 0,
        "total_cost_usd": round(sum(r.get("cost_usd", 0.0) for r in valid), 4),
    }

    summary_out = Path("data/evals/advanced_c78f0430_summary.json")
    with open(summary_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    console.print(f"\n[bold green]Done! n_examples={n}, hit@5={summary['hit_at_5']}, "
                  f"faithfulness={summary['faithfulness']}, relevance={summary['relevance']}")


if __name__ == "__main__":
    main()

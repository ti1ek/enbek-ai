"""RAGAS evaluation runner for Enbek AI — tests Basic, Advanced, and Graph pipelines.

Uses НП ВС РК golden dataset (data/golden/np_golden.jsonl) which contains
reference_answer — required for Context Recall and Answer Correctness metrics.

Usage:
    # Full run (pipeline + scoring)
    uv run python scripts/run_ragas_evals.py --pipeline all
    uv run python scripts/run_ragas_evals.py --pipeline advanced

    # Score-only on saved intermediate results (skip expensive pipeline calls)
    uv run python scripts/run_ragas_evals.py --score-only data/evals/ragas_inputs_basic_*.jsonl
    uv run python scripts/run_ragas_evals.py --score-only data/evals/ragas_inputs_basic_*.jsonl --metrics faithfulness

    # Ablation flags
    ENABLE_HYDE=false uv run python scripts/run_ragas_evals.py --pipeline advanced
"""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, ".")

from packages.config import settings

os.environ["LANGCHAIN_TRACING_V2"] = str(settings.langsmith_tracing).lower()
os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
)
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from datasets import Dataset
from rich.console import Console
from rich.table import Table

console = Console()

GOLDEN_FILE = Path("data/golden/np_golden.jsonl")
RESULTS_DIR = Path("data/evals")

ALL_METRICS = {
    "faithfulness": faithfulness,
    "answer_relevancy": answer_relevancy,
    "context_precision": context_precision,
    "context_recall": context_recall,
    "answer_correctness": answer_correctness,
}


def load_golden() -> list[dict]:
    items = []
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _context_texts_from_basic(result: dict) -> list[str]:
    """Extract actual chunk texts from basic_rag result."""
    return [s.get("text", s.get("url", "")) for s in result["sources"][:5] if s.get("text") or s.get("url")]


def _context_texts_from_graph(graph_result: dict) -> list[str]:
    """Split graph context string into individual chunks."""
    ctx = graph_result.get("context", "")
    if ctx:
        parts = [p.strip() for p in ctx.split("---") if p.strip()]
        return parts[:5] if parts else [ctx]
    return [s.get("url", "") for s in graph_result.get("sources", [])[:5]]


def run_pipeline(question: str, pipeline: str) -> dict:
    t0 = time.perf_counter()
    if pipeline == "basic":
        from packages.rag.basic_rag import basic_rag
        result = basic_rag(question)
        return {
            "answer": result["answer"],
            "contexts": _context_texts_from_basic(result),
            "latency_ms": result["latency_ms"],
        }
    else:
        from apps.api.graph import run_graph
        graph_result = run_graph(question, pipeline="advanced")
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "answer": graph_result["answer"],
            "contexts": _context_texts_from_graph(graph_result),
            "latency_ms": latency_ms,
        }


def _get_llm_embeddings():
    llm = LangchainLLMWrapper(ChatOpenAI(
        model=settings.llm_mini_model,
        api_key=settings.openai_api_key,
        temperature=0.0,
    ))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    ))
    return llm, embeddings


def score_dataset(rows: list[dict], metric_names: list[str], pipeline_label: str) -> dict:
    """Run RAGAS scoring on pre-collected rows."""
    selected_metrics = [ALL_METRICS[m] for m in metric_names if m in ALL_METRICS]
    if not selected_metrics:
        console.print("[red]No valid metrics selected")
        return {}

    dataset = Dataset.from_list(rows)
    llm, embeddings = _get_llm_embeddings()

    console.print(f"[bold]Running RAGAS scoring: {metric_names}...")
    scores = evaluate(
        dataset=dataset,
        metrics=selected_metrics,
        llm=llm,
        embeddings=embeddings,
    )

    scores_dict = scores.to_pandas().select_dtypes(include="number").mean().to_dict()
    scores_dict = {k: round(float(v), 3) for k, v in scores_dict.items()}

    summary = {
        "pipeline": pipeline_label,
        "n_examples": len(rows),
        **scores_dict,
    }

    table = Table(title=f"RAGAS Results — {pipeline_label.upper()}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    for k, v in summary.items():
        table.add_row(str(k), str(v))
    console.print(table)

    run_id = str(uuid.uuid4())[:8]
    out = RESULTS_DIR / f"ragas_{pipeline_label}_{run_id}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    console.print(f"[bold green]Saved → {out}")
    return summary


def run_ragas(pipeline: str, golden: list[dict], metric_names: list[str]) -> dict:
    console.print(f"\n[bold blue]Running RAGAS: pipeline={pipeline}, n={len(golden)}")

    rows = []
    latencies = []

    for i, item in enumerate(golden):
        qid = item["id"]
        question = item["question"]
        reference = item["reference_answer"]

        console.print(f"  [{i+1}/{len(golden)}] {qid}: {question[:55]}...")
        try:
            result = run_pipeline(question, pipeline)
            rows.append({
                "question": question,
                "answer": result["answer"],
                "contexts": result["contexts"],
                "reference": reference,
            })
            latencies.append(result["latency_ms"])
            time.sleep(0.3)
        except Exception as e:
            console.print(f"  [red]Error on {qid}: {e}")
            rows.append({
                "question": question,
                "answer": "",
                "contexts": [],
                "reference": reference,
            })
            latencies.append(0)

    # Save intermediate results for --score-only re-use
    run_id = str(uuid.uuid4())[:8]
    inputs_file = RESULTS_DIR / f"ragas_inputs_{pipeline}_{run_id}.jsonl"
    with open(inputs_file, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    console.print(f"[dim]Inputs saved → {inputs_file}")

    summary = score_dataset(rows, metric_names, pipeline)
    summary["avg_latency_ms"] = round(sum(latencies) / len(latencies)) if latencies else 0
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", choices=["basic", "advanced", "graph", "all"], default="all")
    parser.add_argument("--metrics", default="all",
                        help="Comma-separated metrics or 'all'. E.g. faithfulness or faithfulness,context_recall")
    parser.add_argument("--score-only", dest="score_only", default=None,
                        help="Path to saved ragas_inputs_*.jsonl — skip pipeline, run scoring only")
    args = parser.parse_args()

    metric_names = list(ALL_METRICS.keys()) if args.metrics == "all" else [m.strip() for m in args.metrics.split(",")]

    # Score-only mode
    if args.score_only:
        inputs_file = Path(args.score_only)
        rows = [json.loads(l) for l in inputs_file.read_text().splitlines() if l.strip()]
        pipeline_label = inputs_file.stem.replace("ragas_inputs_", "").rsplit("_", 1)[0]
        console.print(f"[bold blue]Score-only mode: {inputs_file.name}, metrics={metric_names}")
        score_dataset(rows, metric_names, pipeline_label)
        return

    golden = load_golden()
    pipelines = ["basic", "advanced", "graph"] if args.pipeline == "all" else [args.pipeline]

    results = {}
    for p in pipelines:
        if p == "graph":
            os.environ["ENABLE_GRAPH_EXPAND"] = "true"
            summary = run_ragas("advanced", golden, metric_names)
            summary["pipeline"] = "graph"
            os.environ["ENABLE_GRAPH_EXPAND"] = "false"
        else:
            summary = run_ragas(p, golden, metric_names)
        results[p] = summary

    if len(results) > 1:
        table = Table(title="RAGAS A/B/C Comparison")
        table.add_column("Metric", style="bold")
        for p in results:
            table.add_column(p.upper(), justify="right")
        for m in metric_names + ["avg_latency_ms"]:
            row = [m]
            for p in results:
                row.append(str(results[p].get(m, "—")))
            table.add_row(*row)
        console.print(table)


if __name__ == "__main__":
    main()

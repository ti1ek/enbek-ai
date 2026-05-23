"""RAGAS evaluation runner for Enbek AI — tests Basic, Advanced, and Graph pipelines.

Uses НП ВС РК golden dataset (data/golden/np_golden.jsonl) which contains
reference_answer — required for Context Recall and Answer Correctness metrics.

Usage:
    uv run python scripts/run_ragas_evals.py --pipeline all
    uv run python scripts/run_ragas_evals.py --pipeline advanced
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


def load_golden() -> list[dict]:
    items = []
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run_pipeline(question: str, pipeline: str) -> dict:
    t0 = time.perf_counter()
    if pipeline == "basic":
        from packages.rag.basic_rag import basic_rag
        result = basic_rag(question)
        return {
            "answer": result["answer"],
            "contexts": [s.get("url", "") + " " + str(s.get("article", "")) for s in result["sources"][:5]],
            "sources": result["sources"],
            "latency_ms": result["latency_ms"],
        }
    else:
        from apps.api.graph import run_graph
        graph_result = run_graph(question, pipeline="advanced")
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "answer": graph_result["answer"],
            "contexts": [s.get("url", "") + " " + str(s.get("article", "")) for s in graph_result["sources"][:5]],
            "sources": graph_result["sources"],
            "latency_ms": latency_ms,
        }


def run_ragas(pipeline: str, golden: list[dict]) -> dict:
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

    dataset = Dataset.from_list(rows)

    llm = LangchainLLMWrapper(ChatOpenAI(
        model=settings.llm_mini_model,
        api_key=settings.openai_api_key,
        temperature=0.0,
    ))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    ))

    console.print("[bold]Running RAGAS scoring...")
    scores = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
            answer_correctness,
        ],
        llm=llm,
        embeddings=embeddings,
    )

    scores_dict = scores.to_pandas().mean().to_dict()
    scores_dict = {k: round(float(v), 3) for k, v in scores_dict.items() if k != "__index_level_0__"}

    summary = {
        "pipeline": pipeline,
        "n_examples": len(rows),
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        **scores_dict,
    }

    table = Table(title=f"RAGAS Results — {pipeline.upper()}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    for k, v in summary.items():
        table.add_row(str(k), str(v))
    console.print(table)

    run_id = str(uuid.uuid4())[:8]
    out = RESULTS_DIR / f"ragas_{pipeline}_{run_id}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    console.print(f"[bold green]Saved → {out}")

    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", choices=["basic", "advanced", "graph", "all"], default="all")
    args = parser.parse_args()

    golden = load_golden()

    pipelines = ["basic", "advanced", "graph"] if args.pipeline == "all" else [args.pipeline]

    results = {}
    for p in pipelines:
        if p == "graph":
            os.environ["ENABLE_GRAPH_EXPAND"] = "true"
            summary = run_ragas("advanced", golden)
            summary["pipeline"] = "graph"
            os.environ["ENABLE_GRAPH_EXPAND"] = "false"
        else:
            summary = run_ragas(p, golden)
        results[p] = summary

    if len(results) > 1:
        table = Table(title="RAGAS A/B/C Comparison")
        table.add_column("Metric", style="bold")
        for p in results:
            table.add_column(p.upper(), justify="right")
        metrics = ["faithfulness", "answer_relevancy", "context_precision", "context_recall", "answer_correctness", "avg_latency_ms"]
        for m in metrics:
            row = [m]
            for p in results:
                row.append(str(results[p].get(m, "—")))
            table.add_row(*row)
        console.print(table)


if __name__ == "__main__":
    main()

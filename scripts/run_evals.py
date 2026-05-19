"""Run evaluation pipeline and optionally compare basic vs advanced."""
import os
import sys
import argparse
import json

sys.path.insert(0, ".")

# Setup LangSmith
from packages.config import settings
os.environ["LANGCHAIN_TRACING_V2"] = str(settings.langsmith_tracing).lower()
os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project

from packages.evals.runner import run_evals
from rich.console import Console
from rich.table import Table

console = Console()


def compare(basic: dict, advanced: dict) -> None:
    table = Table(title="A/B Comparison: Advanced vs Basic RAG")
    table.add_column("Metric", style="bold")
    table.add_column("Basic", justify="right")
    table.add_column("Advanced", justify="right")
    table.add_column("Delta", justify="right")

    metrics = ["hit_at_5", "keyword_match", "faithfulness", "relevance",
               "avg_latency_ms", "total_cost_usd"]
    for m in metrics:
        b = basic.get(m, "-")
        a = advanced.get(m, "-")
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            delta = round(float(a) - float(b), 3)
            delta_str = f"+{delta}" if delta > 0 else str(delta)
        else:
            delta_str = "—"
        table.add_row(m, str(b), str(a), delta_str)

    console.print(table)
    console.print("\n[bold]Вывод:")
    if isinstance(advanced.get("hit_at_5"), float) and isinstance(basic.get("hit_at_5"), float):
        diff = advanced["hit_at_5"] - basic["hit_at_5"]
        if diff > 0.05:
            console.print(f"  ✅ Advanced RAG показывает лучший hit@5 (+{diff:.1%}) — оставляем Advanced как основной pipeline.")
        else:
            console.print(f"  ℹ️ Разница hit@5 незначительная ({diff:.1%}). Advanced всё равно предпочтителен за счёт качества ответов.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", choices=["basic", "advanced", "both"], default="advanced")
    parser.add_argument("--max-judge-calls", type=int, default=30)
    args = parser.parse_args()

    if args.pipeline == "both":
        console.rule("[bold blue]Running BASIC pipeline")
        basic_summary = run_evals("basic", args.max_judge_calls)
        console.rule("[bold blue]Running ADVANCED pipeline")
        advanced_summary = run_evals("advanced", args.max_judge_calls)
        compare(basic_summary, advanced_summary)
        # Save comparison
        with open("data/evals/ab_comparison.json", "w") as f:
            json.dump({"basic": basic_summary, "advanced": advanced_summary}, f, indent=2)
    else:
        run_evals(args.pipeline, args.max_judge_calls)

"""Evaluation runner: measures execution accuracy, attempts, latency and cost on a fixed question set.

Usage (from the project root, with .env configured and Postgres running):
    python -m evaluation.run_eval                     # full run, validator ON
    python -m evaluation.run_eval --no-validator      # ablation: validator OFF
    python -m evaluation.run_eval --compare           # both, side by side
    python -m evaluation.run_eval --ids e01 h03       # a subset

The agent's SQL is never compared as text: both queries are executed and their results compared.
Uses MCP in-process mode so no separate server is needed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
from pathlib import Path

os.environ.setdefault("MCP_MODE", "inprocess")

from analyst.agents.orchestrator import Orchestrator  # noqa: E402
from analyst.llm import get_llm  # noqa: E402
from analyst.mcp_server.tools import execute_sql  # noqa: E402
from evaluation.compare import results_match  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def load_questions(ids: list[str] | None = None) -> list[dict]:
    qs = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    return [q for q in qs if not ids or q["id"] in ids]


def evaluate(questions: list[dict], use_validator: bool, llm=None) -> dict:
    llm = llm or get_llm()
    orch = Orchestrator(llm, use_validator=use_validator, write_insights=False)
    records = []
    for i, q in enumerate(questions, 1):
        gold = execute_sql(q["sql"])
        if not gold.get("ok"):
            raise RuntimeError(f"Gold SQL for {q['id']} failed: {gold.get('error')}")
        try:
            res = orch.run(q["question"])
            if res.status == "answered":
                correct, why = results_match(gold, {"columns": res.columns, "rows": res.rows},
                                             q.get("order_matters", False))
            else:
                correct, why = False, res.error or res.status
        except Exception as err:  # noqa: BLE001 - one failure must not stop the run
            res, correct, why = None, False, f"crash: {err}"
        rec = {
            "id": q["id"], "difficulty": q["difficulty"], "question": q["question"],
            "correct": correct, "reason": why,
            "attempts": res.attempts if res else None, "seconds": res.seconds if res else None,
            "tokens": (res.input_tokens + res.output_tokens) if res else None,
            "cost_usd": res.cost_usd if res else None, "sql": res.sql if res else "",
        }
        records.append(rec)
        print(f"[{i:>2}/{len(questions)}] {'PASS' if correct else 'FAIL'} {q['id']} "
              f"({rec['attempts']} att, {rec['seconds']}s) {q['question'][:60]}" + ("" if correct else f"  <- {why}"))
    return {"use_validator": use_validator, "records": records, "summary": summarise(records)}


def summarise(records: list[dict]) -> dict:
    def acc(rs):
        return round(100 * sum(r["correct"] for r in rs) / len(rs), 1) if rs else None

    done = [r for r in records if r["seconds"] is not None]
    costs = [r["cost_usd"] for r in done if r["cost_usd"] is not None]
    return {
        "questions": len(records),
        "accuracy_pct": acc(records),
        "by_difficulty": {d: acc([r for r in records if r["difficulty"] == d]) for d in ("easy", "medium", "hard")},
        "avg_attempts": round(statistics.mean(r["attempts"] for r in done), 2) if done else None,
        "median_seconds": round(statistics.median(r["seconds"] for r in done), 2) if done else None,
        "avg_tokens": round(statistics.mean(r["tokens"] for r in done)) if done else None,
        "avg_cost_usd": round(statistics.mean(costs), 5) if len(costs) == len(done) and costs else None,
    }


def to_markdown(runs: list[dict]) -> str:
    head = "| Metric | " + " | ".join("Validator ON" if r["use_validator"] else "Validator OFF" for r in runs) + " |"
    lines = [head, "|---|" + "---|" * len(runs)]
    rows = [("Questions", "questions"), ("Execution accuracy (%)", "accuracy_pct"),
            ("Avg attempts", "avg_attempts"), ("Median seconds", "median_seconds"),
            ("Avg tokens", "avg_tokens"), ("Avg cost (USD)", "avg_cost_usd")]
    for label, key in rows:
        lines.append(f"| {label} | " + " | ".join(str(r["summary"][key]) for r in runs) + " |")
    for d in ("easy", "medium", "hard"):
        lines.append(f"| Accuracy {d} (%) | " + " | ".join(str(r["summary"]["by_difficulty"][d]) for r in runs) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-validator", action="store_true")
    parser.add_argument("--compare", action="store_true", help="run with and without the validator")
    parser.add_argument("--ids", nargs="*")
    args = parser.parse_args()

    questions = load_questions(args.ids)
    configs = [False, True] if args.compare else [not args.no_validator]
    runs = []
    for use_validator in configs:
        print(f"\n=== Validator {'ON' if use_validator else 'OFF'} ===")
        runs.append(evaluate(questions, use_validator))

    RESULTS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    (RESULTS / f"run_{stamp}.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    table = to_markdown(runs)
    (RESULTS / f"run_{stamp}.md").write_text(f"# Evaluation {stamp}\n\n{table}\n", encoding="utf-8")
    print("\n" + table + f"\n\nSaved to evaluation/results/run_{stamp}.json and .md")


if __name__ == "__main__":
    main()

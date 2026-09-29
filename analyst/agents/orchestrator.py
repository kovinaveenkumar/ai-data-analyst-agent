"""Orchestrator: runs the multi-agent pipeline and records every step.

question -> SQL writer -> validate_sql (MCP) -> execute_sql (MCP) -> result validator
         -> (retry with feedback, up to MAX_ATTEMPTS) -> insight writer -> answer
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from analyst import mcp_client
from analyst.agents import insight_agent, sql_agent, validator
from analyst.config import get_settings
from analyst.llm import LLM


@dataclass
class Step:
    agent: str
    action: str
    detail: str
    ok: bool = True
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    question: str
    status: str  # "answered" | "unanswerable" | "failed"
    sql: str = ""
    reasoning: str = ""
    assumptions: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    truncated: bool = False
    insights: dict = field(default_factory=dict)
    attempts: int = 0
    steps: list[Step] = field(default_factory=list)
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Orchestrator:
    def __init__(self, llm: LLM, use_validator: bool | None = None, max_attempts: int | None = None,
                 write_insights: bool = True):
        settings = get_settings()
        self.llm = llm
        self.use_validator = settings.use_result_validator if use_validator is None else use_validator
        self.max_attempts = max_attempts or settings.max_attempts
        self.write_insights = write_insights

    def run(self, question: str, history: list[dict] | None = None) -> AnalysisResult:
        start = time.perf_counter()
        calls_before = len(self.llm.usage.calls)
        res = AnalysisResult(question=question, status="failed")
        feedback: list[dict] = []
        final: dict | None = None

        for attempt in range(1, self.max_attempts + 1):
            res.attempts = attempt
            draft = sql_agent.generate_sql(self.llm, question, history, feedback)
            sql = (draft.get("sql") or "").strip()
            res.reasoning, res.assumptions = draft.get("reasoning", ""), draft.get("assumptions", [])
            res.steps.append(Step("SQL writer", f"attempt {attempt}", draft.get("reasoning", ""), data={"sql": sql}))

            if not draft.get("answerable", True):
                res.status, res.error = "unanswerable", draft.get("reasoning", "")
                break

            check = mcp_client.call_tool("validate_sql", {"sql": sql})
            if not check.get("ok"):
                problem = "; ".join(check.get("errors", [check.get("error", "invalid SQL")]))
                res.steps.append(Step("MCP validate_sql", f"rejected ({check.get('stage', '?')})", problem, ok=False))
                feedback.append({"sql": sql, "problem": problem})
                continue
            res.steps.append(Step("MCP validate_sql", "passed", "Safety rules and EXPLAIN plan OK"))

            result = mcp_client.call_tool("execute_sql", {"sql": sql})
            if not result.get("ok"):
                res.steps.append(Step("MCP execute_sql", "error", result.get("error", ""), ok=False))
                feedback.append({"sql": sql, "problem": result.get("error", "execution failed")})
                continue
            res.steps.append(Step("MCP execute_sql", "ran",
                                  f"{result['row_count']} rows in {result['elapsed_ms']} ms"))

            problems = validator.rule_checks(question, result)
            if not problems and self.use_validator:
                verdict = validator.review(self.llm, question, result["sql"], result)
                if verdict.get("verdict") == "retry":
                    problems = verdict.get("issues", []) + ([verdict["fix_hint"]] if verdict.get("fix_hint") else [])
            if problems and attempt < self.max_attempts:
                res.steps.append(Step("Result validator", "retry", " | ".join(problems), ok=False))
                feedback.append({"sql": sql, "problem": " ".join(problems)})
                final = result  # keep best-so-far in case later attempts fail
                continue
            res.steps.append(Step("Result validator", "passed" if not problems else "accepted with warnings",
                                  " | ".join(problems) or "Result answers the question"))
            final = result
            break

        if final is not None and res.status != "unanswerable":
            res.status = "answered"
            res.sql, res.columns, res.rows, res.truncated = (
                final["sql"], final["columns"], final["rows"], final["truncated"])
            if self.write_insights:
                try:
                    res.insights = insight_agent.write_insights(self.llm, question, res.sql, final)
                    res.steps.append(Step("Insight writer", "summarised", res.insights.get("headline", "")))
                except Exception as err:  # insights are optional; the data answer still stands
                    res.steps.append(Step("Insight writer", "skipped", str(err), ok=False))
        elif res.status != "unanswerable":
            res.error = feedback[-1]["problem"] if feedback else "No valid query produced."

        new_calls = self.llm.usage.calls[calls_before:]
        res.input_tokens = sum(c.input_tokens + c.cache_read_tokens for c in new_calls)
        res.output_tokens = sum(c.output_tokens for c in new_calls)
        from analyst.llm import UsageTracker

        res.cost_usd = UsageTracker(calls=list(new_calls)).cost_usd()
        res.seconds = round(time.perf_counter() - start, 2)
        return res

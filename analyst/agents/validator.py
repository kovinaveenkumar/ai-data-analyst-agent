"""Result validator: deterministic sanity checks first (free), then a Claude review (cheap model).

It answers one question: does this result actually answer what was asked? If not, it
explains why, and the orchestrator sends that explanation back to the SQL writer.
"""

from __future__ import annotations

from analyst.agents import context
from analyst.llm import LLM, preview_rows

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "retry"]},
        "issues": {"type": "array", "items": {"type": "string"},
                   "description": "Concrete problems, e.g. 'includes cancelled orders', 'wrong year'."},
        "fix_hint": {"type": "string", "description": "How the SQL should change (empty if pass)."},
    },
    "required": ["verdict", "issues", "fix_hint"],
}


def rule_checks(question: str, result: dict) -> list[str]:
    """Cheap checks that need no model call."""
    problems: list[str] = []
    rows = result.get("rows", [])
    if result.get("row_count", 0) == 0:
        problems.append("The query returned no rows. Check filters, date ranges and join conditions.")
    elif all(all(v is None for v in r.values()) for r in rows):
        problems.append("Every value in the result is NULL. Check the aggregation and joins.")
    if result.get("truncated"):
        problems.append("The result hit the row limit; aggregate or add LIMIT for the rows the question needs.")
    q = question.lower()
    if rows and any(w in q for w in ("revenue", "sales", "profit")):
        for r in rows:
            for k, v in r.items():
                if isinstance(v, (int, float)) and v < 0 and "change" not in k and "growth" not in k \
                        and "diff" not in k and "profit" not in k:
                    problems.append(f"Column '{k}' has a negative value ({v}); revenue should not be negative.")
                    return problems
    return problems


def review(llm: LLM, question: str, sql: str, result: dict) -> dict:
    system = (
        "You review SQL results for a data team. Decide if the result correctly and completely answers "
        "the question under the business rules. Be strict about metric definitions, date ranges and "
        "cancelled-order handling, but do not nitpick style, column names or rounding. "
        "Answer 'retry' only for a real correctness problem.\n\n=== BUSINESS RULES ===\n"
        + context.business_rules()
    )
    prompt = f"Question: {question}\n\nSQL:\n{sql}\n\nResult:\n{preview_rows(result, 25)}"
    return llm.structured(agent="validator", fast=True, system=system, prompt=prompt,
                          tool_name="submit_review", schema=SCHEMA, max_tokens=800)

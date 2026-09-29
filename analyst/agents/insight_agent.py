"""Insight writer: plain-English findings plus a chart recommendation (cheap model).

Language models are unreliable at arithmetic over many numbers (e.g. adding 12 monthly
values). So every total, average, share and change is calculated here in Python and
handed to Claude as exact facts; the prompt forbids calculating anything itself.
"""

from __future__ import annotations

import json

from analyst.llm import LLM, preview_rows

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One-sentence direct answer with the key number."},
        "summary": {"type": "string", "description": "2-4 sentences a manager would read."},
        "key_points": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "chart": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["bar", "horizontal_bar", "line", "pie", "scatter", "table"]},
                "x": {"type": "string", "description": "Column for the x axis / categories."},
                "y": {"type": "string", "description": "Numeric column for values."},
                "color": {"type": "string", "description": "Optional column to split series by, or empty."},
                "title": {"type": "string"},
            },
            "required": ["type", "x", "y", "color", "title"],
        },
        "follow_up_questions": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
    },
    "required": ["headline", "summary", "key_points", "chart", "follow_up_questions"],
}


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


RATE_WORDS = ("pct", "percent", "rate", "growth", "share", "margin", "ratio", "change")
ID_WORDS = ("_id", "id", "number", "year", "month", "rank")


def _is_rate(col: str) -> bool:
    return any(w in col.lower() for w in RATE_WORDS)


def _is_identifier(col: str) -> bool:
    c = col.lower()
    return c == "id" or c.endswith("_id") or c.endswith("_number") or c in ("year", "month", "rank", "quarter")


def result_facts(result: dict) -> dict:
    """Exact statistics for every numeric column, computed in Python."""
    rows, columns = result.get("rows", []), result.get("columns", [])
    if not rows:
        return {}
    numeric = [c for c in columns if rows and all(_is_number(r.get(c)) or r.get(c) is None for r in rows)
               and any(_is_number(r.get(c)) for r in rows)]
    labels = [c for c in columns if c not in numeric]
    numeric = [c for c in numeric if not _is_identifier(c)]  # IDs and month numbers are labels, not amounts
    label = labels[0] if labels else None

    def name(row):
        return row.get(label) if label else None

    facts: dict = {"row_count": len(rows)}
    for col in numeric:
        vals = [(r, r[col]) for r in rows if _is_number(r.get(col))]
        if not vals:
            continue
        nums = [v for _, v in vals]
        total = sum(nums)
        hi_row, hi = max(vals, key=lambda x: x[1])
        lo_row, lo = min(vals, key=lambda x: x[1])
        f = {
            "total": round(total, 2),
            "average": round(total / len(nums), 2),
            "max": {"value": round(hi, 2), "at": name(hi_row)},
            "min": {"value": round(lo, 2), "at": name(lo_row)},
        }
        if len(nums) >= 2:
            first, last = nums[0], nums[-1]
            f["first"] = {"value": round(first, 2), "at": name(vals[0][0])}
            f["last"] = {"value": round(last, 2), "at": name(vals[-1][0])}
            if first:
                f["change_first_to_last_pct"] = round(100 * (last - first) / abs(first), 1)
        if total and all(n >= 0 for n in nums) and len(nums) <= 25:
            f["share_of_total_pct"] = {str(name(r)): round(100 * v / total, 1) for r, v in vals}
        if len(nums) >= 2 and len(nums) <= 25:
            f["change_vs_previous_row_pct"] = {
                str(name(vals[i][0])): (round(100 * (nums[i] - nums[i - 1]) / abs(nums[i - 1]), 1)
                                        if nums[i - 1] else None)
                for i in range(1, len(nums))
            }
        if len(nums) >= 4 and len(nums) <= 25:
            span = f"{name(vals[-3][0])} to {name(vals[-1][0])}"  # label the rows explicitly
            f["last_three_rows"] = {
                "rows": span,
                "total": round(sum(nums[-3:]), 2),
                "share_of_total_pct": round(100 * sum(nums[-3:]) / total, 1) if total else None,
            }
            f["last_two_rows"] = {
                "rows": f"{name(vals[-2][0])} to {name(vals[-1][0])}",
                "total": round(sum(nums[-2:]), 2),
                "share_of_total_pct": round(100 * sum(nums[-2:]) / total, 1) if total else None,
            }
        if _is_rate(col):
            # summing or taking shares of percentages is meaningless: keep only range and average
            f = {k: f[k] for k in ("average", "max", "min", "first", "last") if k in f}
            f["note"] = "this column is already a rate/percentage; do not add or compare its values as amounts"
        facts[col] = f
    return facts


def write_insights(llm: LLM, question: str, sql: str, result: dict) -> dict:
    system = (
        "You are a business analyst. Explain query results to a non-technical manager.\n"
        "NUMBERS RULE: never add, average, subtract or compute percentages yourself. Every figure you "
        "write must appear either in the result rows or in the pre-computed FACTS (which are exact). "
        "If a number you want is in neither, describe the pattern in words instead. When you quote a "
        "fact that covers several rows, name exactly the rows it lists (e.g. 'October-December'). "
        "Quarters: Q1 = Jan-Mar, Q2 = Apr-Jun, Q3 = Jul-Sep, Q4 = Oct-Dec.\n"
        "Format money like $1,234,567 (round to whole dollars unless small). "
        "Pick the chart that fits the data: line for time trends, bar/horizontal_bar for rankings and "
        "category comparisons, pie only for 2-6 parts of a whole, 'table' for a single number or wide lists. "
        "Chart x/y/color must be exact column names from the result (color may be an empty string)."
    )
    prompt = (
        f"Question: {question}\n\nSQL:\n{sql}\n\n"
        f"FACTS (exact, computed in Python):\n{json.dumps(result_facts(result), default=str)}\n\n"
        f"Result:\n{preview_rows(result, 60)}"
    )
    return llm.structured(agent="insight_writer", fast=True, system=system, prompt=prompt,
                          tool_name="submit_insights", schema=SCHEMA, max_tokens=1200)

"""Result-set comparison used by the evaluation (execution accuracy).

A prediction is correct when it returns the same rows as the gold query. We compare
*results*, not SQL text, and allow for harmless differences:
  * column names, column order and extra columns in the prediction
  * row order (unless the question requires an order)
  * numeric rounding (relative tolerance 0.5%, absolute 0.05)
  * month labels: 2025-03-01 == 2025-03 == 2025-03-01T00:00:00
"""

from __future__ import annotations

import math
import re
from itertools import permutations

DATE_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?(?:[T ]00:00:00(?:\+00:00)?)?$")


def norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = DATE_RE.match(s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}" if d in (None, "01") else f"{y}-{mo}-{d}"
    try:
        return float(s)
    except ValueError:
        return s.lower()


def same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=5e-3, abs_tol=0.05)
    return a == b


def _col(rows: list[dict], name: str) -> list:
    return [norm(r.get(name)) for r in rows]


def _sort_key(v):
    return (v is None, str(type(v)), v if v is not None else 0)


def _multiset_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    a_s, b_s = sorted(a, key=_sort_key), sorted(b, key=_sort_key)
    return all(same(x, y) for x, y in zip(a_s, b_s))


def results_match(gold: dict, pred: dict, order_matters: bool = False) -> tuple[bool, str]:
    g_rows, p_rows = gold["rows"], pred["rows"]
    if len(g_rows) != len(p_rows):
        return False, f"row count {len(p_rows)} != expected {len(g_rows)}"
    if not g_rows:
        return True, "both empty"
    g_cols, p_cols = gold["columns"], pred["columns"]

    # candidate prediction columns for each gold column (same multiset of values)
    candidates = {g: [p for p in p_cols if _multiset_equal(_col(g_rows, g), _col(p_rows, p))] for g in g_cols}
    missing = [g for g, c in candidates.items() if not c]
    if missing:
        return False, f"no column matching expected column(s) {missing}"

    # try column assignments (tiny search: results have few columns)
    options = [candidates[g] for g in g_cols]
    for assignment in _assignments(options):
        g_tuples = [tuple(norm(r[g]) for g in g_cols) for r in g_rows]
        p_tuples = [tuple(norm(r[p]) for p in assignment) for r in p_rows]
        if order_matters:
            ok = all(all(same(x, y) for x, y in zip(a, b)) for a, b in zip(g_tuples, p_tuples))
        else:
            ok = _rows_equal_unordered(g_tuples, p_tuples)
        if ok:
            return True, "match"
    return False, "values match per column but not row by row" + (" (or order differs)" if order_matters else "")


def _assignments(options: list[list[str]], used: tuple = ()):
    if not options:
        yield used
        return
    for choice in options[0]:
        if choice not in used:
            yield from _assignments(options[1:], used + (choice,))


def _rows_equal_unordered(a: list[tuple], b: list[tuple]) -> bool:
    remaining = list(b)
    for row in a:
        for i, cand in enumerate(remaining):
            if all(same(x, y) for x, y in zip(row, cand)):
                remaining.pop(i)
                break
        else:
            return False
    return True


__all__ = ["results_match", "norm", "same", "permutations"]

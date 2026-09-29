"""Turns the insight writer's chart suggestion into a Plotly figure, with safe fallbacks."""

from __future__ import annotations

import pandas as pd
import plotly.express as px


def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def auto_spec(df: pd.DataFrame) -> dict:
    """Heuristic chart choice when the model's suggestion is missing or unusable."""
    nums = _numeric_columns(df)
    others = [c for c in df.columns if c not in nums]
    if len(df) <= 1 or not nums:
        return {"type": "table"}
    x = others[0] if others else df.columns[0]
    looks_like_time = any(k in x.lower() for k in ("month", "date", "week", "year", "day", "quarter"))
    return {"type": "line" if looks_like_time else "bar", "x": x, "y": nums[0], "color": "", "title": ""}


def build_figure(rows: list[dict], spec: dict | None):
    """Return a Plotly figure, or None when a table is the better view."""
    if not rows:
        return None
    df = pd.DataFrame(rows)
    spec = dict(spec or {})
    cols = set(df.columns)
    if spec.get("type") in (None, "", "table") or spec.get("x") not in cols or spec.get("y") not in cols:
        spec = auto_spec(df) if spec.get("type") != "table" else spec
    kind = spec.get("type", "table")
    if kind == "table" or spec.get("x") not in cols or spec.get("y") not in cols:
        return None
    if not pd.api.types.is_numeric_dtype(df[spec["y"]]):
        return None
    color = spec.get("color") if spec.get("color") in cols else None
    title = spec.get("title") or ""
    x, y = spec["x"], spec["y"]
    if kind == "line":
        fig = px.line(df, x=x, y=y, color=color, markers=True, title=title)
    elif kind == "pie":
        fig = px.pie(df, names=x, values=y, title=title)
    elif kind == "scatter":
        fig = px.scatter(df, x=x, y=y, color=color, title=title)
    elif kind == "horizontal_bar":
        mode = "relative" if df[x].is_unique else "group"
        fig = px.bar(df, x=y, y=x, color=color, orientation="h", title=title, barmode=mode)
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
    else:
        # one bar per x value: stack mode avoids empty gaps when bars are coloured by a category
        mode = "relative" if df[x].is_unique else "group"
        fig = px.bar(df, x=x, y=y, color=color, title=title, barmode=mode,
                     category_orders={x: list(dict.fromkeys(df[x]))})  # keep the query's row order
    fig.update_layout(margin={"l": 10, "r": 10, "t": 50 if title else 20, "b": 10}, legend_title_text="")
    return fig

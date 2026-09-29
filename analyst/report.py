"""Downloadable reports: Markdown and PDF (question, answer, insights, chart, SQL, data)."""

from __future__ import annotations

import datetime as dt
import io
import logging
from typing import Iterable

import pandas as pd
from fpdf import FPDF

from analyst.charts import auto_spec

logging.getLogger("matplotlib.category").setLevel(logging.ERROR)


def _latin1(text: str) -> str:
    # core PDF fonts are Latin-1; replace characters they cannot draw
    replacements = {"\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
                    "\u2022": "-", "\u2192": "->", "\u2026": "..."}
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def to_markdown(results: Iterable[dict], title: str = "Analysis report") -> str:
    out = [f"# {title}", f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M}_", ""]
    for r in results:
        ins = r.get("insights") or {}
        out += [f"## {r['question']}", ""]
        if ins.get("headline"):
            out += [f"**{ins['headline']}**", ""]
        if ins.get("summary"):
            out += [ins["summary"], ""]
        for p in ins.get("key_points", []):
            out.append(f"- {p}")
        if r.get("rows"):
            df = pd.DataFrame(r["rows"]).head(30)
            out += ["", df.to_markdown(index=False), ""]
        if r.get("sql"):
            out += ["<details><summary>SQL</summary>", "", "```sql", r["sql"], "```", "</details>", ""]
    return "\n".join(out)


def _chart_png(rows: list[dict], spec: dict | None) -> bytes | None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if not rows:
        return None
    df = pd.DataFrame(rows)
    spec = spec if spec and spec.get("x") in df.columns and spec.get("y") in df.columns else auto_spec(df)
    if spec.get("type") in (None, "table") or not pd.api.types.is_numeric_dtype(df[spec["y"]]):
        return None
    df = df.head(40)
    fig, ax = plt.subplots(figsize=(7.5, 3.4), dpi=150)
    x, y = df[spec["x"]].astype(str), df[spec["y"]]
    if spec["type"] == "line":
        ax.plot(x, y, marker="o", linewidth=1.8)
    elif spec["type"] == "horizontal_bar":
        ax.barh(x[::-1], y[::-1])
    elif spec["type"] == "pie":
        ax.pie(y, labels=x, autopct="%1.0f%%")
    else:
        ax.bar(x, y)
    if spec["type"] != "pie":
        from matplotlib.ticker import FuncFormatter

        fmt = FuncFormatter(lambda v, _: f"{v:,.0f}")
        (ax.xaxis if spec["type"] == "horizontal_bar" else ax.yaxis).set_major_formatter(fmt)
        ax.set_ylabel(spec["y"].replace("_", " ")) if spec["type"] != "horizontal_bar" else None
        ax.tick_params(axis="x", labelrotation=45 if len(df) > 6 and spec["type"] != "horizontal_bar" else 0,
                       labelsize=7)
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def to_pdf(results: Iterable[dict], title: str = "Analysis report") -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _latin1(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(110)
    pdf.cell(0, 6, f"Generated {dt.datetime.now():%Y-%m-%d %H:%M} by AI Data Analyst Agent",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)

    for r in results:
        ins = r.get("insights") or {}
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 7, _latin1(r["question"]), new_x="LMARGIN", new_y="NEXT")
        if ins.get("headline"):
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(0, 5.5, _latin1(ins["headline"]), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        if ins.get("summary"):
            pdf.multi_cell(0, 5.5, _latin1(ins["summary"]), new_x="LMARGIN", new_y="NEXT")
        for p in ins.get("key_points", []):
            pdf.multi_cell(0, 5.5, _latin1(f"- {p}"), new_x="LMARGIN", new_y="NEXT")
        png = _chart_png(r.get("rows", []), ins.get("chart"))
        if png:
            pdf.ln(2)
            pdf.image(io.BytesIO(png), w=180)
        if r.get("rows"):
            df = pd.DataFrame(r["rows"]).head(15)
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 8)
            with pdf.table(text_align="LEFT", line_height=4.5) as table:
                header = table.row()
                for c in df.columns:
                    header.cell(_latin1(str(c)))
                for _, row in df.iterrows():
                    tr = table.row()
                    for v in row:
                        tr.cell(_latin1(f"{v:,.2f}" if isinstance(v, float) else str(v)))
            if len(r["rows"]) > 15:
                pdf.set_font("Helvetica", "I", 8)
                pdf.cell(0, 5, f"Showing 15 of {len(r['rows'])} rows.", new_x="LMARGIN", new_y="NEXT")
        if r.get("sql"):
            pdf.ln(2)
            pdf.set_font("Courier", "", 7.5)
            pdf.set_fill_color(245, 245, 245)
            pdf.multi_cell(0, 4, _latin1(r["sql"]), fill=True, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())

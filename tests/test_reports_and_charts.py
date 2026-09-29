from analyst.charts import build_figure
from analyst.report import to_markdown, to_pdf

RESULT = {
    "question": "Monthly revenue 2025 — trend?",
    "sql": "SELECT 1",
    "rows": [{"month": "2025-01", "total_revenue": 100.5}, {"month": "2025-02", "total_revenue": 150.25}],
    "insights": {"headline": "Revenue grew 49%.", "summary": "Up.", "key_points": ["Feb > Jan"],
                 "chart": {"type": "line", "x": "month", "y": "total_revenue", "color": "", "title": "t"}},
}


def test_pdf_is_generated():
    pdf = to_pdf([RESULT], title="Test report")
    assert pdf[:4] == b"%PDF" and len(pdf) > 2000


def test_markdown_contains_answer_and_sql():
    md = to_markdown([RESULT])
    assert "Revenue grew 49%." in md and "SELECT 1" in md


def test_chart_uses_suggestion_and_falls_back():
    assert build_figure(RESULT["rows"], RESULT["insights"]["chart"]) is not None
    bad = {"type": "bar", "x": "nope", "y": "nope", "color": "", "title": ""}
    assert build_figure(RESULT["rows"], bad) is not None  # heuristic fallback
    assert build_figure([{"n": 5}], {"type": "table"}) is None


def test_strict_schema_and_json_parsing():
    from analyst.agents.insight_agent import SCHEMA
    from analyst.llm import parse_json_text, strict_schema

    s = strict_schema(SCHEMA)
    assert s["additionalProperties"] is False
    assert s["properties"]["chart"]["additionalProperties"] is False
    assert "maxItems" not in s["properties"]["key_points"]
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Here you go: {"sql": "SELECT 1"} done') == {"sql": "SELECT 1"}


def test_insight_facts_are_exact():
    from analyst.agents.insight_agent import result_facts

    rows = [{"month": f"2025-{m:02d}", "total_revenue": v}
            for m, v in [(1, 390665.21), (2, 356673.39), (3, 385994.26), (4, 423032.13), (5, 433607.43),
                         (6, 429519.81), (7, 484003.09), (8, 432872.71), (9, 485282.51), (10, 490878.43),
                         (11, 885396.73), (12, 991147.52)]]
    f = result_facts({"columns": ["month", "total_revenue"], "rows": rows})["total_revenue"]
    assert f["total"] == 6189073.22
    assert f["max"] == {"value": 991147.52, "at": "2025-12"}
    assert f["min"] == {"value": 356673.39, "at": "2025-02"}
    assert f["change_vs_previous_row_pct"]["2025-11"] == 80.4
    assert f["last_three_rows"] == {"rows": "2025-10 to 2025-12", "total": 2367422.68, "share_of_total_pct": 38.3}
    assert f["last_two_rows"]["rows"] == "2025-11 to 2025-12" and f["last_two_rows"]["share_of_total_pct"] == 30.3


def test_facts_skip_ids_and_treat_rates_as_rates():
    from analyst.agents.insight_agent import result_facts

    rows = [{"customer_id": 7, "month_number": 1, "name": "a", "revenue": 100.0, "yoy_growth_pct": 50.0},
            {"customer_id": 9, "month_number": 2, "name": "b", "revenue": 300.0, "yoy_growth_pct": 20.0}]
    f = result_facts({"columns": list(rows[0]), "rows": rows})
    assert "customer_id" not in f and "month_number" not in f
    assert f["revenue"]["total"] == 400.0
    assert "total" not in f["yoy_growth_pct"] and "change_first_to_last_pct" not in f["yoy_growth_pct"]


def test_coloured_bars_keep_query_order():
    rows = [{"n": "Maya", "seg": "Consumer", "rev": 3.0}, {"n": "Mia", "seg": "Corporate", "rev": 2.0},
            {"n": "Chen", "seg": "Consumer", "rev": 1.0}]
    fig = build_figure(rows, {"type": "bar", "x": "n", "y": "rev", "color": "seg", "title": ""})
    assert fig.layout.barmode == "relative"
    assert list(fig.layout.xaxis.categoryarray) == ["Maya", "Mia", "Chen"]

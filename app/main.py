"""Streamlit web app for the AI Data Analyst Agent.

Run:  streamlit run app/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from analyst import mcp_client  # noqa: E402
from analyst.agents.orchestrator import Orchestrator  # noqa: E402
from analyst.charts import build_figure  # noqa: E402
from analyst.config import get_settings  # noqa: E402
from analyst.llm import get_llm  # noqa: E402
from analyst.report import to_markdown, to_pdf  # noqa: E402
from analyst.skills_runner import load_skills, run_data_quality, run_question_skill  # noqa: E402

st.set_page_config(page_title="AI Data Analyst Agent", page_icon="📊", layout="wide")
settings = get_settings()

EXAMPLES = [
    "What was monthly revenue in 2025?",
    "Which 5 product categories generated the most revenue last year?",
    "How has the share of mobile orders changed by quarter?",
    "What is the return rate by category, and which reason is most common?",
    "Who are our top 10 customers by lifetime revenue?",
    "Compare average order value by customer segment in 2024 vs 2025.",
]

# ---------------------------------------------------------------- state
ss = st.session_state
ss.setdefault("history", [])       # list of AnalysisResult dicts
ss.setdefault("questions_used", 0)
ss.setdefault("pending", None)


@st.cache_resource(show_spinner=False)
def llm_client():
    return get_llm()


@st.cache_data(ttl=600, show_spinner=False)
def load_schema() -> dict:
    return mcp_client.call_tool("get_db_schema")


def connection_status() -> tuple[bool, str]:
    try:
        schema = load_schema()
        if schema.get("ok"):
            return True, f"Connected via MCP ({settings.mcp_mode}) · {len(schema['tables'])} tables"
        return False, schema.get("error", "Schema unavailable")
    except Exception as err:  # noqa: BLE001
        return False, str(err)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("📊 AI Data Analyst")
    st.caption("Ask business questions in plain English. Claude writes the SQL, checks it, runs it "
               "through a read-only MCP server and explains the result.")
    ok, msg = connection_status()
    (st.success if ok else st.error)(msg)
    if not settings.anthropic_api_key:
        st.warning("ANTHROPIC_API_KEY is not set - add it to .env")

    use_validator = st.toggle("Result-validation agent", value=settings.use_result_validator,
                              help="A second Claude call checks the result answers the question; "
                                   "problems are sent back to the SQL writer for a retry.")
    st.caption(f"Questions this session: {ss.questions_used}/{settings.max_questions_per_session}")

    if ok:
        with st.expander("Schema explorer"):
            for name, table in load_schema()["tables"].items():
                st.markdown(f"**{name}** · ~{table['approx_rows']:,} rows")
                st.caption(table["description"])
                st.dataframe(pd.DataFrame(table["columns"])[["name", "type", "description"]],
                             hide_index=True, width="stretch")
    if ss.history and st.button("Clear conversation", width="stretch"):
        ss.history = []
        st.rerun()


def run_question(question: str) -> None:
    if ss.questions_used >= settings.max_questions_per_session:
        st.error("Session question limit reached. Refresh the page to start a new session.")
        return
    ss.questions_used += 1
    orchestrator = Orchestrator(llm_client(), use_validator=use_validator)
    history = [{"question": h["question"], "sql": h["sql"]} for h in ss.history if h.get("sql")]
    with st.status("Working on it...", expanded=False) as status:
        status.write("SQL writer drafting a query -> MCP validation -> execution -> result check -> insights")
        result = orchestrator.run(question, history=history)
        status.update(label="Done" if result.status == "answered" else "Could not answer",
                      state="complete" if result.status == "answered" else "error")
    ss.history.append(result.to_dict())


def md(text: str) -> str:
    """Streamlit reads $...$ as LaTeX math, which garbles money values; escape the dollar signs."""
    return (text or "").replace("$", "\\$")


def render_result(r: dict, idx: int) -> None:
    ins = r.get("insights") or {}
    with st.chat_message("user"):
        st.write(r["question"])
    with st.chat_message("assistant"):
        if r["status"] == "unanswerable":
            st.warning(f"This data can't answer that question. {r.get('error', '')}")
            return
        if r["status"] != "answered":
            st.error(f"I couldn't produce a working query after {r['attempts']} attempts. {r.get('error', '')}")
            _trace(r)
            return
        if ins.get("headline"):
            st.markdown(f"#### {md(ins['headline'])}")
        if ins.get("summary"):
            st.markdown(md(ins["summary"]))
        for p in ins.get("key_points", []):
            st.markdown(f"- {md(p)}")
        if r.get("assumptions"):
            st.caption(md("Assumptions: " + "; ".join(r["assumptions"])))

        fig = build_figure(r["rows"], ins.get("chart"))
        if fig is not None:
            st.plotly_chart(fig, width="stretch", key=f"fig{idx}")
        st.dataframe(pd.DataFrame(r["rows"]), hide_index=True, width="stretch")
        if r.get("truncated"):
            st.caption(f"Showing the first {settings.max_rows:,} rows.")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Time", f"{r['seconds']:.1f}s")
        c2.metric("Attempts", r["attempts"])
        c3.metric("Tokens", f"{r['input_tokens'] + r['output_tokens']:,}")
        c4.metric("Cost", f"${r['cost_usd']:.4f}" if r.get("cost_usd") is not None else "n/a")

        with st.expander("SQL"):
            st.code(r["sql"], language="sql")
        _trace(r)

        d1, d2, d3 = st.columns(3)
        d1.download_button("PDF report", to_pdf([r], title=r["question"]), file_name=f"analysis_{idx + 1}.pdf",
                           mime="application/pdf", key=f"pdf{idx}", width="stretch")
        d2.download_button("Markdown", to_markdown([r], title=r["question"]), file_name=f"analysis_{idx + 1}.md",
                           key=f"md{idx}", width="stretch")
        d3.download_button("CSV data", pd.DataFrame(r["rows"]).to_csv(index=False), file_name=f"data_{idx + 1}.csv",
                           key=f"csv{idx}", width="stretch")

        follow = ins.get("follow_up_questions") or []
        if follow and idx == len(ss.history) - 1:
            st.caption("Follow-up ideas")
            cols = st.columns(len(follow))
            for j, q in enumerate(follow):
                if cols[j].button(q, key=f"fu{idx}_{j}", width="stretch"):
                    ss.pending = q
                    st.rerun()


def _trace(r: dict) -> None:
    with st.expander("How the agents worked it out"):
        for s in r["steps"]:
            icon = "✅" if s["ok"] else "🔁"
            st.markdown(f"{icon} **{s['agent']}** - {s['action']}")
            if s["detail"]:
                st.caption(md(s["detail"]))
            if s["data"].get("sql"):
                st.code(s["data"]["sql"], language="sql")


# ---------------------------------------------------------------- tabs
tab_ask, tab_reports, tab_quality, tab_about = st.tabs(["Ask", "Reports (Skills)", "Data quality", "How it works"])

with tab_ask:
    if not ss.history:
        st.markdown("### Ask anything about the e-commerce data")
        st.caption("Orders, revenue, products, customers, channels and returns, Jan 2024 - Dec 2025.")
        cols = st.columns(3)
        for i, q in enumerate(EXAMPLES):
            if cols[i % 3].button(q, key=f"ex{i}", width="stretch"):
                ss.pending = q
                st.rerun()
    for i, r in enumerate(ss.history):
        render_result(r, i)
    typed = st.chat_input("e.g. Which channel grew fastest in 2025?")
    question = typed or ss.pending
    if question:
        ss.pending = None
        run_question(question)
        st.rerun()

with tab_reports:
    skills = [s for s in load_skills() if s.questions]
    st.markdown("### One-click reports")
    st.caption("Each report is an Agent Skill (skills/*/SKILL.md). The same files work in Claude Code "
               "connected to this MCP server.")
    for skill in skills:
        with st.container(border=True):
            st.markdown(f"**{skill.name}**")
            st.caption(skill.description)
            month = st.text_input("Month (YYYY-MM)", value="2025-12", key=f"m_{skill.name}")
            if st.button("Generate report", key=f"run_{skill.name}"):
                bar = st.progress(0.0)
                results = run_question_skill(
                    skill, Orchestrator(llm_client(), use_validator=use_validator), {"month": month},
                    progress=lambda i, n, q: bar.progress(i / n, text=f"{i}/{n}: {q}"),
                )
                ss[f"report_{skill.name}"] = (month, results)
            if f"report_{skill.name}" in ss:
                month_done, results = ss[f"report_{skill.name}"]
                title = f"Monthly Sales Report - {month_done}"
                st.download_button("Download PDF", to_pdf(results, title=title), file_name=f"sales_{month_done}.pdf",
                                   mime="application/pdf", key=f"dl_{skill.name}")
                for j, r in enumerate(results):
                    ins = r.get("insights") or {}
                    st.markdown(f"**{r['question']}**")
                    st.markdown(md(ins.get("headline", r.get("error", ""))))
                    fig = build_figure(r["rows"], ins.get("chart"))
                    if fig is not None:
                        st.plotly_chart(fig, width="stretch", key=f"rep{skill.name}{j}")

with tab_quality:
    st.markdown("### Data-quality audit")
    st.caption("Runs the MCP `data_quality_check` tool: NULLs, duplicate emails, orphan records, invalid values.")
    if st.button("Run audit"):
        ss.dq = run_data_quality()
    if ss.get("dq"):
        dq = ss.dq
        if not dq.get("ok"):
            st.error(dq.get("error"))
        else:
            c1, c2 = st.columns(2)
            c1.metric("Checks run", dq["checks_run"])
            c2.metric("Warnings", dq["warnings"])
            df = pd.DataFrame(dq["checks"])
            st.dataframe(df.sort_values(["status", "issues"], ascending=[False, False]),
                         hide_index=True, width="stretch")

with tab_about:
    arch = Path(__file__).resolve().parent.parent / "docs" / "architecture.md"
    st.markdown(arch.read_text(encoding="utf-8") if arch.exists() else "See docs/architecture.md")

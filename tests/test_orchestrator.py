"""Multi-agent pipeline with a scripted LLM: no API key or network needed."""

from analyst.agents.orchestrator import Orchestrator
from analyst.llm import ScriptedLLM
from tests.conftest import needs_db

pytestmark = needs_db

GOOD_SQL = ("SELECT o.channel, ROUND(SUM(oi.line_total), 2) AS revenue FROM orders o "
            "JOIN order_items oi USING (order_id) WHERE o.status <> 'cancelled' GROUP BY 1 ORDER BY 2 DESC")
INSIGHT = {"headline": "Web leads.", "summary": "s", "key_points": [], "follow_up_questions": [],
           "chart": {"type": "bar", "x": "channel", "y": "revenue", "color": "", "title": "t"}}
PASS = {"verdict": "pass", "issues": [], "fix_hint": ""}


def draft(sql, answerable=True):
    return {"reasoning": "r", "sql": sql, "assumptions": [], "answerable": answerable}


def test_answers_on_first_try():
    llm = ScriptedLLM({"sql_writer": [draft(GOOD_SQL)], "validator": [PASS], "insight_writer": [INSIGHT]})
    res = Orchestrator(llm, use_validator=True).run("Revenue by channel?")
    assert res.status == "answered" and res.attempts == 1 and len(res.rows) == 3
    assert res.insights["headline"] == "Web leads."


def test_self_repairs_after_database_error():
    llm = ScriptedLLM({"sql_writer": [draft("SELECT revenue FROM orders"), draft(GOOD_SQL)],
                       "validator": [PASS], "insight_writer": [INSIGHT]})
    res = Orchestrator(llm, use_validator=True).run("Revenue by channel?")
    assert res.status == "answered" and res.attempts == 2
    # the database error was fed back to the SQL writer
    second_prompt = [p for a, p in llm.prompts if a == "sql_writer"][1]
    assert "revenue" in second_prompt and "does not exist" in second_prompt


def test_blocks_unsafe_sql_and_retries():
    llm = ScriptedLLM({"sql_writer": [draft("DELETE FROM orders"), draft(GOOD_SQL)],
                       "validator": [PASS], "insight_writer": [INSIGHT]})
    res = Orchestrator(llm, use_validator=True).run("Revenue by channel?")
    assert res.status == "answered" and res.steps[1].ok is False


def test_validator_retry_feedback_reaches_sql_writer():
    wrong = GOOD_SQL.replace("WHERE o.status <> 'cancelled' ", "")
    llm = ScriptedLLM({
        "sql_writer": [draft(wrong), draft(GOOD_SQL)],
        "validator": [{"verdict": "retry", "issues": ["includes cancelled orders"], "fix_hint": "exclude cancelled"},
                      PASS],
        "insight_writer": [INSIGHT],
    })
    res = Orchestrator(llm, use_validator=True).run("Revenue by channel?")
    assert res.attempts == 2 and "cancelled" in res.sql
    assert "includes cancelled orders" in [p for a, p in llm.prompts if a == "sql_writer"][1]


def test_unanswerable_question():
    llm = ScriptedLLM({"sql_writer": [draft("SELECT 1", answerable=False)]})
    res = Orchestrator(llm).run("What is the weather in Paris?")
    assert res.status == "unanswerable"


def test_gives_up_after_max_attempts():
    llm = ScriptedLLM({"sql_writer": [draft("SELECT nope FROM orders")] * 3})
    res = Orchestrator(llm, max_attempts=3).run("?")
    assert res.status == "failed" and res.attempts == 3 and "nope" in res.error

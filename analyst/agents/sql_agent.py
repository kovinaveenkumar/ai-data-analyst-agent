"""SQL specialist: turns a question (plus any feedback from failed attempts) into one PostgreSQL SELECT."""

from __future__ import annotations

from analyst.agents import context
from analyst.llm import LLM

SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string", "description": "Short plan: tables, joins, filters, metric definition."},
        "sql": {"type": "string", "description": "One PostgreSQL SELECT statement."},
        "assumptions": {
            "type": "array", "items": {"type": "string"},
            "description": "Interpretations made where the question was ambiguous (may be empty).",
        },
        "answerable": {"type": "boolean", "description": "False if the data cannot answer the question."},
    },
    "required": ["reasoning", "sql", "assumptions", "answerable"],
}


def system_prompt() -> str:
    return f"""You are a senior analytics engineer writing PostgreSQL for an e-commerce company.

Write exactly ONE read-only SELECT query (CTEs allowed) that answers the question.
Use only the tables and columns in the schema below. Follow the business rules exactly;
they define how metrics such as revenue are calculated. Keep the result small and readable:
aggregate instead of returning raw rows unless the question asks for a list.
If the question cannot be answered from this data, set answerable=false and explain in reasoning.

=== SCHEMA ===
{context.schema_text()}

=== BUSINESS RULES ===
{context.business_rules()}

=== EXAMPLES ===
{context.examples_text()}"""


def generate_sql(llm: LLM, question: str, history: list[dict] | None = None,
                 feedback: list[dict] | None = None) -> dict:
    parts: list[str] = []
    if history:
        parts.append("Earlier in this conversation (use for follow-up questions like 'now split by region'):")
        for turn in history[-3:]:
            parts.append(f"- Q: {turn['question']}\n  SQL: {turn['sql']}")
        parts.append("")
    parts.append(f"Question: {question}")
    if feedback:
        parts.append("\nYour previous attempts failed. Fix the problem described; do not repeat the mistake.")
        for i, fb in enumerate(feedback, 1):
            parts.append(f"Attempt {i} SQL:\n{fb['sql']}\nProblem: {fb['problem']}")
    return llm.structured(
        agent="sql_writer", fast=False, system=system_prompt(), prompt="\n".join(parts),
        tool_name="submit_sql", schema=SCHEMA, max_tokens=2000,
    )

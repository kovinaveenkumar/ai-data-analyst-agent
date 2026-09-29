"""Builds the context every agent sees: schema (from MCP), business rules and examples."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from analyst import mcp_client

KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge"


def schema_to_text(schema: dict) -> str:
    lines: list[str] = []
    for name, table in schema["tables"].items():
        lines.append(f"TABLE {name} (~{table['approx_rows']:,} rows) -- {table['description']}")
        for col in table["columns"]:
            desc = f" -- {col['description']}" if col["description"] else ""
            null = "" if col["nullable"] else " NOT NULL"
            lines.append(f"  {col['name']} {col['type']}{null}{desc}")
        for fk in table["foreign_keys"]:
            lines.append(f"  FK {fk}")
        lines.append("")
    return "\n".join(lines).strip()


@lru_cache(maxsize=1)
def business_rules() -> str:
    return (KNOWLEDGE / "business_rules.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def examples_text() -> str:
    examples = json.loads((KNOWLEDGE / "examples.json").read_text(encoding="utf-8"))
    return "\n\n".join(f"Q: {e['question']}\nSQL: {e['sql']}" for e in examples)


_schema_cache: dict[str, str] = {}


def schema_text() -> str:
    """Fetched through the MCP get_db_schema tool once per process."""
    if "text" not in _schema_cache:
        result = mcp_client.call_tool("get_db_schema")
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Could not load the database schema."))
        _schema_cache["text"] = schema_to_text(result)
    return _schema_cache["text"]

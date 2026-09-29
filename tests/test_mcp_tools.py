"""The MCP server through the real MCP client (in-process transport)."""

from analyst import mcp_client
from tests.conftest import needs_db

EXPECTED_TOOLS = {"get_db_schema", "get_sample_rows", "validate_sql", "execute_sql", "data_quality_check"}


def test_server_exposes_expected_tools():
    names = {t["name"] for t in mcp_client.list_tools()}
    assert EXPECTED_TOOLS <= names


def test_execute_blocks_writes_before_touching_database():
    result = mcp_client.call_tool("execute_sql", {"sql": "DELETE FROM orders"})
    assert result["ok"] is False and result["stage"] == "safety"


@needs_db
def test_schema_has_descriptions_and_foreign_keys():
    schema = mcp_client.call_tool("get_db_schema")
    assert schema["ok"]
    assert set(schema["tables"]) == {"customers", "categories", "products", "orders", "order_items", "returns"}
    line_total = next(c for c in schema["tables"]["order_items"]["columns"] if c["name"] == "line_total")
    assert "revenue" in line_total["description"].lower()
    assert schema["tables"]["orders"]["foreign_keys"]


@needs_db
def test_validate_catches_unknown_column_without_running():
    result = mcp_client.call_tool("validate_sql", {"sql": "SELECT revenue FROM orders"})
    assert result["ok"] is False and result["stage"] == "database"
    assert "revenue" in result["errors"][0]


@needs_db
def test_execute_returns_rows():
    result = mcp_client.call_tool("execute_sql", {"sql": "SELECT channel, COUNT(*) AS n FROM orders GROUP BY 1"})
    assert result["ok"] and result["row_count"] == 3 and set(result["columns"]) == {"channel", "n"}


@needs_db
def test_sample_rows_rejects_unknown_table():
    assert mcp_client.call_tool("get_sample_rows", {"table": "pg_shadow"})["ok"] is False
    assert mcp_client.call_tool("get_sample_rows", {"table": "orders", "limit": 3})["row_count"] == 3


@needs_db
def test_data_quality_finds_seeded_issues():
    result = mcp_client.call_tool("data_quality_check", {})
    warned = {c["check"] for c in result["checks"] if c["status"] == "warn"}
    assert {"null_values", "duplicate_emails"} <= warned

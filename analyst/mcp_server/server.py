"""MCP server exposing safe, read-only database tools (MCP Python SDK v2, `MCPServer`).

Run it:
    python -m analyst.mcp_server.server                       # Streamable HTTP on 127.0.0.1:8000/mcp
    python -m analyst.mcp_server.server --transport stdio     # for Claude Desktop / Claude Code

Because it speaks standard MCP, the same server also works outside this app:
    claude mcp add analytics -- python -m analyst.mcp_server.server --transport stdio
"""

from __future__ import annotations

import argparse
import os

from mcp.server.mcpserver import MCPServer

from analyst.mcp_server import tools

mcp = MCPServer(
    "ai-data-analyst",
    instructions=(
        "Read-only access to an e-commerce analytics PostgreSQL database (schema 'shop'). "
        "Call get_db_schema first, check queries with validate_sql, then run them with execute_sql. "
        "Revenue = SUM(order_items.line_total) excluding orders with status 'cancelled'."
    ),
)


@mcp.tool()
def get_db_schema() -> dict:
    """Return every table with its columns, data types, plain-English descriptions and foreign keys."""
    return tools.get_db_schema()


@mcp.tool()
def get_sample_rows(table: str, limit: int = 5) -> dict:
    """Return up to 20 example rows from one table so you can see real value formats."""
    return tools.get_sample_rows(table, limit)


@mcp.tool()
def validate_sql(sql: str) -> dict:
    """Check a query WITHOUT running it: safety rules (single read-only SELECT on allowed tables)
    plus a PostgreSQL EXPLAIN that catches wrong column or table names. Returns errors to fix."""
    return tools.validate_sql(sql)


@mcp.tool()
def execute_sql(sql: str) -> dict:
    """Run one read-only SELECT query and return columns and rows (max 1,000 rows, 30-second timeout)."""
    return tools.execute_sql(sql)


@mcp.tool()
def data_quality_check(table: str | None = None) -> dict:
    """Profile data quality (NULLs, duplicate emails, orphan records, invalid values) for one table or all."""
    return tools.data_quality_check(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Data Analyst MCP server")
    parser.add_argument("--transport", choices=["streamable-http", "stdio"], default="streamable-http")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8000")))
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

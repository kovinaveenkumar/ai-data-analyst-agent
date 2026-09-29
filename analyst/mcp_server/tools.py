"""Plain-Python implementations of the MCP tools.

Kept separate from server.py so they can be unit-tested directly and reused
by the in-process MCP mode. Every tool returns a JSON-serialisable dict and
never raises: errors come back as {"ok": False, "error": "..."} so Claude can
read the message and repair its query.
"""

from __future__ import annotations

from functools import lru_cache

import psycopg
from psycopg import sql as pgsql

from analyst import db
from analyst.config import get_settings
from analyst.sql_safety import ALLOWED_TABLES, validate_sql as static_validate


def _error(message: str, **extra) -> dict:
    return {"ok": False, "error": message, **extra}


def _clean_pg_error(err: Exception) -> str:
    text = str(err).strip()
    # keep the useful first lines (message + HINT), drop connection noise
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return " ".join(lines[:3])[:500]


@lru_cache(maxsize=1)
def _schema_cached(schema: str) -> dict:
    tables: dict[str, dict] = {}
    with db.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname AS table_name, obj_description(c.oid) AS table_comment,
                   c.reltuples::bigint AS approx_rows
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relkind = 'r'
            ORDER BY c.relname
            """,
            (schema,),
        )
        for row in cur.fetchall():
            if row["table_name"] in ALLOWED_TABLES:
                tables[row["table_name"]] = {
                    "description": row["table_comment"] or "",
                    "approx_rows": max(int(row["approx_rows"]), 0),
                    "columns": [],
                    "foreign_keys": [],
                }
        cur.execute(
            """
            SELECT cols.table_name, cols.column_name, cols.data_type, cols.is_nullable,
                   col_description((quote_ident(cols.table_schema)||'.'||quote_ident(cols.table_name))::regclass,
                                   cols.ordinal_position) AS column_comment
            FROM information_schema.columns cols
            WHERE cols.table_schema = %s
            ORDER BY cols.table_name, cols.ordinal_position
            """,
            (schema,),
        )
        for row in cur.fetchall():
            if row["table_name"] in tables:
                tables[row["table_name"]]["columns"].append(
                    {
                        "name": row["column_name"],
                        "type": row["data_type"],
                        "nullable": row["is_nullable"] == "YES",
                        "description": row["column_comment"] or "",
                    }
                )
        # pg_catalog (not information_schema) so a read-only, non-owner role can see the keys
        cur.execute(
            """
            SELECT src.relname AS table_name, a.attname AS column_name,
                   dst.relname AS ref_table, af.attname AS ref_column
            FROM pg_constraint con
            JOIN pg_class src ON src.oid = con.conrelid
            JOIN pg_class dst ON dst.oid = con.confrelid
            JOIN pg_namespace n ON n.oid = src.relnamespace
            JOIN pg_attribute a  ON a.attrelid = con.conrelid  AND a.attnum = con.conkey[1]
            JOIN pg_attribute af ON af.attrelid = con.confrelid AND af.attnum = con.confkey[1]
            WHERE con.contype = 'f' AND n.nspname = %s
            ORDER BY 1, 2
            """,
            (schema,),
        )
        for row in cur.fetchall():
            if row["table_name"] in tables:
                tables[row["table_name"]]["foreign_keys"].append(
                    f"{row['column_name']} -> {row['ref_table']}.{row['ref_column']}"
                )
    return {"ok": True, "schema": schema, "tables": tables}


def get_db_schema() -> dict:
    """Tables, columns, types, descriptions and foreign keys of the analytics schema."""
    try:
        return _schema_cached(get_settings().db_schema)
    except psycopg.Error as err:
        return _error(f"Could not read schema: {_clean_pg_error(err)}")


def get_sample_rows(table: str, limit: int = 5) -> dict:
    """A few example rows from one table, to show real value formats."""
    table = (table or "").strip().lower()
    if table not in ALLOWED_TABLES:
        return _error(f"Unknown table '{table}'. Available: {sorted(ALLOWED_TABLES)}")
    limit = max(1, min(int(limit), 20))
    try:
        with db.connect() as conn:
            query = pgsql.SQL("SELECT * FROM {} LIMIT {}").format(
                pgsql.Identifier(table), pgsql.Literal(limit)
            ).as_string(conn)
        result = db.run_query(query, max_rows=limit)
        return {"ok": True, "table": table, **result}
    except psycopg.Error as err:
        return _error(_clean_pg_error(err))


def validate_sql(sql: str) -> dict:
    """Static safety checks + a Postgres EXPLAIN (plans the query without running it)."""
    settings = get_settings()
    check = static_validate(sql, max_rows=settings.max_rows, schema=settings.db_schema)
    if not check.ok:
        return {"ok": False, "stage": "safety", "errors": check.errors}
    try:
        with db.connect() as conn, conn.cursor() as cur:
            cur.execute("EXPLAIN " + check.sql)
    except psycopg.Error as err:
        return {"ok": False, "stage": "database", "errors": [_clean_pg_error(err)], "safe_sql": check.sql}
    return {"ok": True, "safe_sql": check.sql, "tables": check.tables}


def execute_sql(sql: str) -> dict:
    """Validate (again: never trust the caller) and run a read-only query."""
    checked = validate_sql(sql)
    if not checked["ok"]:
        return {"ok": False, "stage": checked["stage"], "error": "; ".join(checked["errors"])}
    try:
        result = db.run_query(checked["safe_sql"])
    except psycopg.errors.QueryCanceled:
        return _error("Query timed out. Simplify it or filter to a smaller date range.", stage="database")
    except psycopg.Error as err:
        return _error(_clean_pg_error(err), stage="database")
    return {"ok": True, "sql": checked["safe_sql"], **result}


def data_quality_check(table: str | None = None) -> dict:
    """Profile data quality: NULLs, duplicates, orphan keys, invalid values."""
    targets = [table.lower()] if table else sorted(ALLOWED_TABLES)
    unknown = [t for t in targets if t not in ALLOWED_TABLES]
    if unknown:
        return _error(f"Unknown table(s): {unknown}")

    schema = get_db_schema()
    if not schema["ok"]:
        return schema

    checks: list[dict] = []

    def add(check: str, tbl: str, issue_count: int, detail: str) -> None:
        checks.append(
            {
                "check": check,
                "table": tbl,
                "issues": int(issue_count),
                "status": "pass" if issue_count == 0 else "warn",
                "detail": detail,
            }
        )

    try:
        with db.connect() as conn, conn.cursor() as cur:
            for tbl in targets:
                cols = schema["tables"][tbl]["columns"]
                cur.execute(pgsql.SQL("SELECT COUNT(*) AS n FROM {}").format(pgsql.Identifier(tbl)))
                total = cur.fetchone()["n"]
                nullable = [c["name"] for c in cols if c["nullable"]]
                if nullable:
                    parts = pgsql.SQL(", ").join(
                        pgsql.SQL("COUNT(*) FILTER (WHERE {} IS NULL) AS {}").format(
                            pgsql.Identifier(c), pgsql.Identifier(c)
                        )
                        for c in nullable
                    )
                    cur.execute(pgsql.SQL("SELECT {} FROM {}").format(parts, pgsql.Identifier(tbl)))
                    for col, n in cur.fetchone().items():
                        pct = (100.0 * n / total) if total else 0
                        add("null_values", tbl, n, f"{col}: {n} NULLs ({pct:.1f}% of {total} rows)")

            fixed_checks = {
                "customers": [
                    ("duplicate_emails",
                     "SELECT COALESCE(SUM(c - 1), 0) AS n FROM (SELECT COUNT(*) c FROM customers "
                     "WHERE email IS NOT NULL GROUP BY lower(email) HAVING COUNT(*) > 1) d",
                     "customers sharing the same email address"),
                ],
                "orders": [
                    ("orders_without_items",
                     "SELECT COUNT(*) AS n FROM orders o WHERE NOT EXISTS "
                     "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)",
                     "orders that have no line items"),
                    ("orders_before_signup",
                     "SELECT COUNT(*) AS n FROM orders o JOIN customers c USING (customer_id) "
                     "WHERE o.order_date < c.signup_date",
                     "orders dated before the customer signed up"),
                    ("future_orders",
                     "SELECT COUNT(*) AS n FROM orders WHERE order_date > CURRENT_DATE",
                     "orders dated in the future"),
                ],
                "order_items": [
                    ("price_below_cost",
                     "SELECT COUNT(*) AS n FROM order_items i JOIN products p USING (product_id) "
                     "WHERE i.unit_price * (1 - i.discount) < p.unit_cost",
                     "discounted lines sold below unit cost"),
                ],
                "returns": [
                    ("refund_exceeds_line",
                     "SELECT COUNT(*) AS n FROM returns r JOIN order_items i USING (order_item_id) "
                     "WHERE r.refund_amount > i.line_total",
                     "refunds larger than the line value"),
                    ("return_before_order",
                     "SELECT COUNT(*) AS n FROM returns r JOIN order_items i USING (order_item_id) "
                     "JOIN orders o USING (order_id) WHERE r.return_date < o.order_date",
                     "returns dated before the order"),
                ],
                "products": [
                    ("inactive_products_sold",
                     "SELECT COUNT(DISTINCT p.product_id) AS n FROM products p JOIN order_items i "
                     "USING (product_id) WHERE NOT p.is_active",
                     "inactive products that still appear in orders"),
                ],
            }
            for tbl in targets:
                for name, query, detail in fixed_checks.get(tbl, []):
                    cur.execute(query)
                    n = cur.fetchone()["n"]
                    add(name, tbl, n, f"{n} {detail}")
    except psycopg.Error as err:
        return _error(_clean_pg_error(err))

    warnings = [c for c in checks if c["status"] == "warn"]
    return {
        "ok": True,
        "tables_checked": targets,
        "checks_run": len(checks),
        "warnings": len(warnings),
        "checks": checks,
    }

"""Layer 2 of the safety design: static SQL validation before anything reaches the database.

Layer 1 is the read-only database role (db/init/03_readonly_role.sql).
Layer 3 is the runtime guard in db.py (read-only transaction, timeout, row cap).

Rules enforced here:
  * exactly one statement
  * the statement is a SELECT (CTEs / UNION allowed); no DML, DDL, COPY, SET, CALL ...
  * only tables from the allowed analytics schema
  * no dangerous server functions (pg_sleep, pg_read_file, dblink, ...)
  * a LIMIT is added (or tightened) so results stay bounded
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

ALLOWED_TABLES = {"customers", "categories", "products", "orders", "order_items", "returns"}

ALLOWED_TABLE_FUNCTIONS = {"generate_series", "exploding_generate_series", "unnest", "explode"}

FORBIDDEN_FUNCTIONS = {
    "pg_sleep", "pg_sleep_for", "pg_sleep_until", "pg_read_file", "pg_read_binary_file",
    "pg_ls_dir", "pg_stat_file", "lo_import", "lo_export", "dblink", "dblink_exec",
    "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf", "set_config",
    "current_setting", "pg_advisory_lock", "txid_current", "nextval", "setval",
    "query_to_xml", "copy",
}

FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.Command, exp.Grant, exp.TruncateTable, exp.Copy, exp.Set, exp.Transaction,
    exp.Commit, exp.Rollback, exp.Into,
)


@dataclass
class SafetyResult:
    ok: bool
    sql: str = ""  # the (possibly LIMIT-adjusted) SQL that may run
    errors: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)


def validate_sql(sql: str, max_rows: int = 1000, schema: str = "shop") -> SafetyResult:
    """Return a SafetyResult. `ok=False` means the query must not run."""
    text = (sql or "").strip().rstrip(";").strip()
    if not text:
        return SafetyResult(ok=False, errors=["Empty query."])

    try:
        statements = [s for s in sqlglot.parse(text, read="postgres") if s is not None]
    except sqlglot.errors.ParseError as err:
        return SafetyResult(ok=False, errors=[f"SQL could not be parsed: {str(err).splitlines()[0]}"])

    if len(statements) != 1:
        return SafetyResult(ok=False, errors=["Only one SQL statement is allowed."])

    tree = statements[0]
    errors: list[str] = []

    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        errors.append(f"Only SELECT queries are allowed (got {tree.key.upper()}).")

    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            errors.append(f"Forbidden operation: {node.key.upper()}.")
        if isinstance(node, exp.Lock):
            errors.append("Row locking (FOR UPDATE / FOR SHARE) is not allowed.")

    for func in tree.find_all(exp.Func):
        name = (func.sql_name() if not isinstance(func, exp.Anonymous) else func.name).lower()
        if name in FORBIDDEN_FUNCTIONS:
            errors.append(f"Function not allowed: {name}().")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        if isinstance(table.this, exp.Func):  # table functions such as generate_series(...)
            fname = (table.this.name if isinstance(table.this, exp.Anonymous) else table.this.sql_name()).lower()
            if fname not in ALLOWED_TABLE_FUNCTIONS:
                errors.append(f"Table function not allowed: {fname}().")
            continue
        name = table.name.lower()
        db = (table.db or "").lower()
        if name in cte_names and not db:
            continue
        if db and db != schema:
            errors.append(f"Schema not allowed: {db}. Only '{schema}' can be queried.")
            continue
        if name not in ALLOWED_TABLES:
            errors.append(f"Unknown or disallowed table: {name}.")
            continue
        tables.add(name)

    if errors:
        # de-duplicate while keeping order
        return SafetyResult(ok=False, errors=list(dict.fromkeys(errors)))

    tree = _enforce_limit(tree, max_rows)
    return SafetyResult(ok=True, sql=tree.sql(dialect="postgres"), tables=sorted(tables))


def _enforce_limit(tree: exp.Expression, max_rows: int) -> exp.Expression:
    limit = tree.args.get("limit")
    if limit is not None:
        try:
            current = int(limit.expression.name)
            if current <= max_rows:
                return tree
        except (AttributeError, ValueError):
            pass
    return tree.limit(max_rows, copy=True) if hasattr(tree, "limit") else tree

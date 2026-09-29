"""Layer 3 of the safety design: every query runs in a READ ONLY transaction with a timeout and a row cap."""

from __future__ import annotations

import datetime as dt
import decimal
import time
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row, tuple_row

from analyst.config import get_settings


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(settings.database_url, connect_timeout=10, row_factory=dict_row) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {int(settings.statement_timeout_ms)}")
            cur.execute("SET search_path TO " + psycopg.sql.Identifier(settings.db_schema).as_string(conn))
        yield conn


def to_jsonable(value: Any) -> Any:
    """Postgres types (Decimal, date, ...) -> plain JSON values."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return value.total_seconds()
    if isinstance(value, (bytes, memoryview)):
        return "<binary>"
    return value


def unique_names(names: list[str]) -> list[str]:
    """Postgres allows duplicate column names (e.g. two COUNT(*)); dict rows would silently drop one."""
    seen: dict[str, int] = {}
    out = []
    for name in names:
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 1
            out.append(name)
    return out


def run_query(sql: str, params: tuple | dict | None = None, max_rows: int | None = None) -> dict:
    """Run an already-validated SELECT. Returns columns, rows (list of dicts) and timing."""
    settings = get_settings()
    cap = max_rows or settings.max_rows
    start = time.perf_counter()
    with connect() as conn, conn.cursor(row_factory=tuple_row) as cur:
        cur.execute(sql, params)
        rows = cur.fetchmany(cap + 1)
        columns = unique_names([d.name for d in cur.description] if cur.description else [])
    truncated = len(rows) > cap
    rows = rows[:cap]
    return {
        "columns": columns,
        "rows": [{k: to_jsonable(v) for k, v in zip(columns, r)} for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
    }


def ping() -> bool:
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False

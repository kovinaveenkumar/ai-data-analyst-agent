"""Safety layer 2: static SQL validation. No database needed."""

import pytest

from analyst.sql_safety import validate_sql

BLOCKED = [
    "DELETE FROM orders",
    "UPDATE orders SET status = 'delivered'",
    "INSERT INTO orders VALUES (1, 1, '2025-01-01', 'delivered', 'web')",
    "DROP TABLE orders",
    "TRUNCATE orders",
    "ALTER TABLE orders ADD COLUMN x int",
    "CREATE TABLE x (id int)",
    "GRANT ALL ON orders TO public",
    "SELECT 1; DROP TABLE orders",
    "SELECT * FROM orders; DELETE FROM orders",
    "SELECT pg_sleep(60)",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT * FROM dblink('host=evil', 'select 1') AS t(x int)",
    "SELECT set_config('statement_timeout', '0', false)",
    "SELECT * FROM pg_user",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM public.secrets",
    "SELECT * INTO backup FROM orders",
    "SELECT * FROM orders FOR UPDATE",
    "COPY orders TO '/tmp/out.csv'",
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
    "",
    "this is not sql",
]


@pytest.mark.parametrize("sql", BLOCKED)
def test_dangerous_queries_are_blocked(sql):
    result = validate_sql(sql)
    assert not result.ok, f"should be blocked: {sql!r}"
    assert result.errors


ALLOWED = [
    "SELECT COUNT(*) FROM orders",
    "SELECT * FROM shop.orders",
    "WITH m AS (SELECT order_id FROM orders) SELECT COUNT(*) FROM m",
    "SELECT channel FROM orders UNION SELECT reason FROM returns",
    "SELECT d::date FROM generate_series('2024-01-01'::date, '2024-03-01'::date, '1 month') d",
    "SELECT o.order_id FROM orders o WHERE EXISTS (SELECT 1 FROM returns r)",
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_normal_analytics_queries_pass(sql):
    result = validate_sql(sql)
    assert result.ok, result.errors


def test_limit_is_added_when_missing():
    assert validate_sql("SELECT * FROM orders", max_rows=1000).sql.endswith("LIMIT 1000")


def test_large_limit_is_capped_and_small_limit_kept():
    assert validate_sql("SELECT * FROM orders LIMIT 50000", max_rows=1000).sql.endswith("LIMIT 1000")
    assert validate_sql("SELECT * FROM orders LIMIT 5", max_rows=1000).sql.endswith("LIMIT 5")


def test_tables_are_reported():
    result = validate_sql("SELECT * FROM orders JOIN order_items USING (order_id)")
    assert result.tables == ["order_items", "orders"]

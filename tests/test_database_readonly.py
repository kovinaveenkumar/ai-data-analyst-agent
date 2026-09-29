"""Safety layers 1 and 3: even SQL that bypasses the validator cannot write."""

import psycopg
import pytest

from analyst import db
from tests.conftest import needs_db

pytestmark = needs_db

WRITES = [
    "DELETE FROM orders",
    "UPDATE customers SET email = NULL",
    "INSERT INTO categories VALUES (99, 'Hacked')",
    "CREATE TABLE evil (id int)",
    "DROP TABLE returns",
]


@pytest.mark.parametrize("sql", WRITES)
def test_database_role_refuses_writes(sql):
    # call the DB layer directly, skipping the SQL validator on purpose
    with pytest.raises(psycopg.Error):
        db.run_query(sql)


def test_row_cap_applies():
    result = db.run_query("SELECT * FROM order_items", max_rows=10)
    assert result["row_count"] == 10 and result["truncated"] is True


def test_duplicate_column_names_are_kept():
    result = db.run_query("SELECT 1 AS n, 2 AS n")
    assert result["columns"] == ["n", "n_2"] and result["rows"] == [{"n": 1, "n_2": 2}]

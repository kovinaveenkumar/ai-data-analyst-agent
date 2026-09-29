from evaluation.compare import results_match


def r(columns, rows):
    return {"columns": columns, "rows": [dict(zip(columns, row)) for row in rows]}


def test_ignores_column_names_order_and_extra_columns():
    gold = r(["month", "rev"], [("2025-01-01", 100.0), ("2025-02-01", 200.0)])
    pred = r(["orders", "m", "revenue"], [(5, "2025-01", 100.004), (7, "2025-02", 199.999)])
    assert results_match(gold, pred, order_matters=True)[0]


def test_row_order_only_matters_when_required():
    gold = r(["c", "n"], [("a", 1), ("b", 2)])
    pred = r(["c", "n"], [("b", 2), ("a", 1)])
    assert results_match(gold, pred)[0]
    assert not results_match(gold, pred, order_matters=True)[0]


def test_wrong_values_fail():
    gold = r(["n"], [(100.0,)])
    assert not results_match(gold, r(["n"], [(110.0,)]))[0]
    assert not results_match(gold, r(["n"], [(100.0,), (1.0,)]))[0]


def test_rows_must_line_up_not_just_columns():
    gold = r(["c", "n"], [("a", 1), ("b", 2)])
    pred = r(["c", "n"], [("a", 2), ("b", 1)])
    assert not results_match(gold, pred)[0]

# Data dictionary

Synthetic e-commerce data, generated deterministically by `db/init/02_seed.sql`
(same data on every fresh database). Orders run from 2024-01-01 to 2025-12-31.

| Table | Rows (approx.) | Description |
|---|---|---|
| customers | 2,000 | Registered customers: name, email, city, state, segment, signup date |
| categories | 8 | Product categories |
| products | 120 | Catalogue: price, unit cost, active flag |
| orders | 27,000 | One row per order: date, status, channel |
| order_items | 68,000 | Order lines: quantity, unit price, discount, `line_total` |
| returns | 2,400 | Returned lines with reason and refund |

## Metric definitions

The agents follow `analyst/knowledge/business_rules.md`. The key ones:

- **Revenue** = `SUM(order_items.line_total)` for orders that are not cancelled.
- **Average order value** = revenue / distinct non-cancelled orders.
- **Gross profit** = revenue - `SUM(quantity * products.unit_cost)`.
- **Return rate** = returned lines / lines of delivered orders.

## Patterns built into the data

Year-over-year growth, a November/December holiday peak, mobile's share rising over time, and a few
deliberate data-quality issues (about 1% NULL emails, 3 duplicate emails, inactive products still in
orders) for the data-quality check to find.

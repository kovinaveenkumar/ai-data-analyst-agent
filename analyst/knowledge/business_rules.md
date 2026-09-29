# Business rules (read these before writing SQL)

- Database: PostgreSQL 16, schema `shop` (search_path is already set; plain table names work).
- Data covers orders from 2024-01-01 to 2025-12-31. Relative phrases refer to the data:
  "last year" / "this year" = 2025, "the previous year" = 2024, "last month" = December 2025,
  "last quarter" = Q4 2025.
- **Revenue** = SUM(order_items.line_total) for orders whose status is NOT 'cancelled'.
  line_total already includes quantity and discount. Never use products.list_price for revenue.
- **Orders** (counts) exclude cancelled orders unless the question is about cancellations.
- **Average order value (AOV)** = revenue / COUNT(DISTINCT order_id), non-cancelled orders only.
- **Gross profit** = revenue - SUM(order_items.quantity * products.unit_cost), non-cancelled orders.
- **Units sold** = SUM(order_items.quantity), non-cancelled orders.
- **Return rate** = returned order lines / order lines of delivered orders.
- **Refunds** = SUM(returns.refund_amount). Net revenue = revenue - refunds.
- **Active customer** = customer with at least one non-cancelled order in the period.
- **New customer in a month** = the month of the customer's first non-cancelled order.
- Months: group with DATE_TRUNC('month', order_date)::date, label as TO_CHAR(..., 'YYYY-MM') when helpful.
- Round money to 2 decimals and percentages to 1 decimal.
- Always ORDER BY something meaningful (time ascending for trends, value descending for rankings).
- Give columns readable snake_case aliases (e.g. total_revenue, order_count).

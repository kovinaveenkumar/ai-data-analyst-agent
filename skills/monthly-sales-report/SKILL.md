---
name: monthly-sales-report
description: Produce a standard monthly sales report for the e-commerce analytics database - revenue trend, category mix, channel mix, top products and returns for a given month. Use when someone asks for a monthly sales report, month-end summary or sales recap.
---

# Monthly Sales Report

Use the `analytics` MCP server tools (`get_db_schema`, `validate_sql`, `execute_sql`).
Follow the business rules in `analyst/knowledge/business_rules.md` (revenue excludes cancelled orders).

## Inputs
- `month`: the report month as YYYY-MM. Default: the latest month in the data (2025-12).

## Questions
1. What was total revenue, order count and average order value in {month}, compared with the previous month?
2. What was revenue by product category in {month}, highest first?
3. What share of {month} revenue came from each sales channel?
4. What were the top 5 products by revenue in {month}?
5. What was the return rate and total refund amount for orders placed in {month}?

## Output format
1. One-paragraph executive summary with the three most important numbers.
2. One section per question: the answer in a sentence, a small table, and a chart where useful.
3. Close with 2-3 recommended follow-up questions.

## Rules
- Validate every query with `validate_sql` before `execute_sql`.
- State month-over-month changes as percentages rounded to 1 decimal.
- Never invent numbers; every figure must come from a query result.

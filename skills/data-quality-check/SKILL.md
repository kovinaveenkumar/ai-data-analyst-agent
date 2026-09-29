---
name: data-quality-check
description: Run a data-quality audit of the e-commerce analytics database - NULLs, duplicate emails, orphan records and invalid values - and explain the business impact. Use when someone asks whether the data can be trusted, for a data audit or before building a new report.
---

# Data Quality Check

Use the `analytics` MCP server's `data_quality_check` tool (optionally with one `table`).

## Steps
1. Call `data_quality_check` with no table to profile every table.
2. For each check with status `warn`, explain in one sentence what it means for reporting
   (e.g. "NULL emails do not affect revenue but block email campaigns for these customers").
3. Rank the warnings by business impact: High (affects revenue or customer counts), Medium, Low.
4. Suggest a concrete fix for each warning (e.g. a constraint, a cleaning step, a source-system fix).

## Output format
- A summary line: checks run, warnings found, overall verdict (Trusted / Use with care / Not reliable).
- A table: check, table, issues, impact, suggested fix.

## Rules
- Report exactly the counts the tool returns.
- Do not run any query that modifies data; the database connection is read-only anyway.

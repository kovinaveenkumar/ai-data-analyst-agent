# Design decisions

Rewrite these in your own words as you build confidence with the code; interviewers ask "why".

**Multiple agents instead of one big prompt.** One prompt that writes SQL, judges it and explains it
tends to approve its own mistakes. A separate validator with a different job catches problems such
as including cancelled orders or the wrong year, and its reason goes back to the SQL writer.
Measure the effect with `python -m evaluation.run_eval --compare`.

**MCP between the agents and the database.** The tools are defined once, with their safety rules,
and any MCP client can use them: this app, Claude Code (`.mcp.json`), or Claude Desktop. The agent
code never holds a database connection.

**Validate before executing.** `validate_sql` runs the safety rules plus a Postgres `EXPLAIN`, which
catches wrong column names without running the query. Errors go back to Claude word for word.

**Three safety layers, not one.** Static SQL checks can have gaps; the read-only role and read-only
transaction make a gap harmless.

**Two model sizes.** The main model writes SQL (hardest step). The faster, cheaper model validates
and summarises. The evaluation reports cost so the trade-off is measured, not guessed.

**Business rules as a file.** Metric definitions live in `analyst/knowledge/business_rules.md`,
not in code. Changing what "revenue" means is a one-line edit that the whole system picks up.

**Few-shot examples separate from the test set.** `analyst/knowledge/examples.json` never overlaps
`evaluation/questions.json`, so the accuracy number is not inflated by memorised answers.

**Compare results, not SQL text.** Two different queries can both be right. The evaluation runs
both and compares rows, allowing for column names, extra columns, row order and rounding.

**Deterministic seed data.** Everyone who clones the repo gets identical data, so evaluation
results are reproducible.

**Known limitations** (good to mention honestly): the data is synthetic; the validator is itself an
LLM and can be wrong; very ambiguous questions get an assumption rather than a clarifying question;
one database dialect (PostgreSQL) is supported.

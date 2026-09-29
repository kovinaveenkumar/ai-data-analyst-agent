# Resume and LinkedIn material

Fill every `[ ]` with your real numbers from `evaluation/results/`. Never publish a number you
did not measure.

## Resume project entry

**AI Data Analyst Agent** | Python, Claude API, Model Context Protocol, PostgreSQL, Streamlit | [GitHub] [Live demo]

- Built a multi-agent AI analyst that answers plain-English business questions over a 6-table,
  ~68k-row PostgreSQL e-commerce database, returning SQL, charts, insights and PDF reports.
- Designed a custom MCP server (5 tools) with three safety layers (read-only role, AST-based SQL
  validation, runtime limits); 50+ automated tests confirm no write or unsafe query can run.
- Added a result-validation agent with self-correcting retries; raised execution accuracy from
  [__]% to [__]% on a 30-question benchmark (easy/medium/hard) at a median [__] s per question.
- Set up CI with GitHub Actions, Docker Compose and reproducible seed data; packaged repeatable
  reports as Agent Skills usable from Claude Code.

## LinkedIn - Experience or Projects entry

**Title:** Independent AI Engineering Project - AI Data Analyst Agent
**Dates:** [month you started] - [month you finished]
**Description:**
Built an AI data analyst that turns plain-English questions into verified SQL, charts and reports.
Claude agents write, check and explain queries; a custom MCP server gives them safe, read-only
access to PostgreSQL. Measured [__]% execution accuracy on a 30-question benchmark.
Skills: Claude API · Model Context Protocol · AI Agents · LLM Evaluation · SQL · PostgreSQL · Python · Streamlit

## LinkedIn launch post (edit into your own voice)

> I just finished building an AI Data Analyst Agent.
>
> You ask a business question in plain English - "What was monthly revenue in 2025?" - and a team
> of Claude agents writes the SQL, checks it, runs it through a read-only MCP server, and explains
> the answer with a chart.
>
> What I learned:
> - A second "validator" agent made a real difference: accuracy went from [__]% to [__]% on my
>   30-question test set.
> - Safety has to be layered. The database role, SQL parsing and runtime limits each block
>   different failure modes.
> - Measuring beats guessing. The evaluation harness changed how I made every design decision.
>
> Demo: [link] · Code: [link]
> #AI #DataAnalytics #Claude #MCP #SQL #Python

## Interview questions to prepare

1. Walk me through the architecture. (Use docs/architecture.md.)
2. How do you stop the model from running a destructive query? (Three layers; show the tests.)
3. How did you measure accuracy, and why compare results instead of SQL text?
4. Which questions still fail, and why? (Look at the FAIL lines in your eval output.)
5. Why multiple agents? What did the validator cost in time and tokens?
6. How would you scale this for a company with 500 tables? (Retrieve only relevant tables,
   semantic layer, caching, per-user permissions.)

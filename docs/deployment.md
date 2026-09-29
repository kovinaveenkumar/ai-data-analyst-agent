# Deployment

## 1. Local (recommended first)

```bash
docker compose up -d postgres          # database with schema, data and read-only role
python -m analyst.mcp_server.server    # terminal 1: MCP server on http://127.0.0.1:8000/mcp
streamlit run app/main.py              # terminal 2: web app on http://localhost:8501
```

Simplest variant: set `MCP_MODE=inprocess` in `.env` and skip terminal 1.

Everything in containers: `docker compose --profile full up --build`.

## 2. Free public demo: Streamlit Community Cloud + hosted Postgres

1. **Database.** Create a free Postgres on Neon or Supabase. Load the three files in `db/init/`
   in order with `psql "<owner connection string>" -f db/init/01_schema.sql` (then 02, 03).
   Change the `analyst_ro` password in `03_readonly_role.sql` before running it.
   If the provider does not allow `CREATE ROLE` in SQL, create a role in its dashboard and
   `GRANT USAGE ON SCHEMA shop` + `GRANT SELECT ON ALL TABLES IN SCHEMA shop` to it.
2. **App.** Push the repo to GitHub, then create an app on share.streamlit.io with
   main file `app/main.py`.
3. **Secrets** (app settings -> Secrets), as TOML:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   DATABASE_URL = "postgresql://analyst_ro:<password>@<host>/<db>?sslmode=require"
   MCP_MODE = "inprocess"
   MAX_QUESTIONS_PER_SESSION = "10"
   ```
   Root-level secrets are exposed as environment variables, which is what `analyst/config.py` reads.
   Use `inprocess` here because Community Cloud runs a single process.
4. **Protect your budget.** Set a monthly spend limit in the Claude Console and keep
   `MAX_QUESTIONS_PER_SESSION` low.
5. Test the link in a private browser window and on a phone before sharing it.

Free tiers and their limits change; check each provider's current terms.

## 3. Optional: host the MCP server separately

Run `python -m analyst.mcp_server.server --host 0.0.0.0 --port 8000` on any container host
(Render, Fly.io, Railway), put it behind HTTPS, and set `MCP_MODE=http` and
`MCP_SERVER_URL=https://<your-host>/mcp` in the app. Add authentication before exposing it publicly:
anyone who can reach the endpoint can run read-only queries.

A public HTTPS endpoint is also what Claude's API-side MCP connector needs if you later want Claude
to call the tools directly from the Messages API instead of through this app's orchestrator; see the
MCP connector page in the Claude API docs.

## 4. Use the server from Claude Code

The repo includes `.mcp.json`. Open the project folder in Claude Code and the `analytics` server is
offered automatically; the `skills/` folder contains the two Agent Skills.

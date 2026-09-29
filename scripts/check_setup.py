"""Run this first: checks every piece the app needs and says exactly what to fix.

    python -m scripts.check_setup
"""

from __future__ import annotations

import sys

from analyst.config import get_settings


def main() -> int:
    s = get_settings()
    ok = True

    def report(passed: bool, label: str, fix: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"  {'OK  ' if passed else 'FAIL'} {label}" + ("" if passed else f"\n       -> {fix}"))

    print("\n1. Configuration")
    report(bool(s.anthropic_api_key), "ANTHROPIC_API_KEY is set", "Copy .env.example to .env and add your key.")

    print("\n2. Database (read-only role)")
    from analyst import db

    up = db.ping()
    report(up, f"Connect to {s.database_url.split('@')[-1]}", "Start it: docker compose up -d postgres")
    if up:
        try:
            db.run_query("CREATE TABLE should_fail (id int)")
            report(False, "Role is read-only", "Use the analyst_ro user in DATABASE_URL, not postgres.")
        except Exception:  # noqa: BLE001
            report(True, "Role is read-only (write was refused)")

    print(f"\n3. MCP server (mode: {s.mcp_mode})")
    from analyst import mcp_client

    try:
        tools = [t["name"] for t in mcp_client.list_tools()]
        report(len(tools) >= 5, f"Reached server, tools: {', '.join(tools)}")
    except Exception as err:  # noqa: BLE001
        report(False, "Reach MCP server", f"Start it: python -m analyst.mcp_server.server  ({err})")

    print("\n4. Claude API")
    if s.anthropic_api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=s.anthropic_api_key)
            for model in (s.main_model, s.fast_model):
                client.messages.create(model=model, max_tokens=5, messages=[{"role": "user", "content": "hi"}])
                report(True, f"Model {model} responds")
        except Exception as err:  # noqa: BLE001
            report(False, "Call Claude", f"Check the key and model names in .env ({type(err).__name__}: {err})")
    else:
        report(False, "Call Claude", "Set ANTHROPIC_API_KEY first.")

    print("\nAll good - run: streamlit run app/main.py\n" if ok else "\nFix the FAIL items above, then run again.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

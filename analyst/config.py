"""Central settings, read once from environment variables (or a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

try:  # python-dotenv is optional at runtime
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


def _float_or_none(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


@dataclass(frozen=True)
class Settings:
    # --- Claude ---
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    # Main model writes and repairs SQL; fast model handles lighter steps (validation, insights).
    # Check https://docs.claude.com for current model names and update .env if they change.
    main_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MAIN_MODEL", "claude-sonnet-5-5"))
    fast_model: str = field(default_factory=lambda: os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-4-5-20251001"))
    # Optional prices (USD per million tokens) so the app can show cost. Leave blank to show tokens only.
    main_input_price: float | None = field(default_factory=lambda: _float_or_none("MAIN_INPUT_PRICE_PER_MTOK"))
    main_output_price: float | None = field(default_factory=lambda: _float_or_none("MAIN_OUTPUT_PRICE_PER_MTOK"))
    fast_input_price: float | None = field(default_factory=lambda: _float_or_none("FAST_INPUT_PRICE_PER_MTOK"))
    fast_output_price: float | None = field(default_factory=lambda: _float_or_none("FAST_OUTPUT_PRICE_PER_MTOK"))

    # --- Database (read-only role!) ---
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "postgresql://analyst_ro:analyst_ro_pw@localhost:5432/analytics"
        )
    )
    db_schema: str = field(default_factory=lambda: os.getenv("DB_SCHEMA", "shop"))
    max_rows: int = field(default_factory=lambda: int(os.getenv("MAX_ROWS", "1000")))
    statement_timeout_ms: int = field(default_factory=lambda: int(os.getenv("STATEMENT_TIMEOUT_MS", "30000")))

    # --- MCP ---
    # "inprocess" runs the MCP server inside the app process (simplest, used by tests and eval).
    # "http" connects to a separately running server at MCP_SERVER_URL (Streamable HTTP).
    mcp_mode: str = field(default_factory=lambda: os.getenv("MCP_MODE", "http"))
    mcp_server_url: str = field(default_factory=lambda: os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp"))

    # --- Agent behaviour ---
    max_attempts: int = field(default_factory=lambda: int(os.getenv("MAX_ATTEMPTS", "3")))
    use_result_validator: bool = field(
        default_factory=lambda: os.getenv("USE_RESULT_VALIDATOR", "true").lower() in {"1", "true", "yes"}
    )
    max_questions_per_session: int = field(
        default_factory=lambda: int(os.getenv("MAX_QUESTIONS_PER_SESSION", "25"))
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

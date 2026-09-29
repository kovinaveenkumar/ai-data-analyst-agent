"""Thin client the agents use to call MCP tools.

MCP_MODE=http       -> talk to a separately running server over Streamable HTTP (production shape)
MCP_MODE=inprocess  -> connect to the same MCPServer object in-process (tests, evaluation, simple demos)

Either way the agent goes through the real MCP protocol client, never around it.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from mcp import Client

from analyst.config import get_settings


class MCPToolError(RuntimeError):
    pass


def _target():
    settings = get_settings()
    if settings.mcp_mode == "inprocess":
        from analyst.mcp_server.server import mcp as server

        return server
    return settings.mcp_server_url


def _decode(result) -> dict:
    if getattr(result, "structured_content", None):
        data = result.structured_content
        return data.get("result", data) if isinstance(data, dict) else {"ok": True, "result": data}
    text = "".join(getattr(block, "text", "") for block in result.content or [])
    if getattr(result, "is_error", False):
        return {"ok": False, "error": text or "Tool call failed."}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"ok": True, "result": text}


async def call_tool_async(name: str, arguments: dict[str, Any] | None = None) -> dict:
    try:
        async with Client(_target(), read_timeout_seconds=60) as client:
            result = await client.call_tool(name, arguments or {})
    except Exception as err:  # connection problems -> readable message
        raise MCPToolError(
            f"Could not reach the MCP server ({type(err).__name__}: {err}). "
            "Is it running? Start it with: python -m analyst.mcp_server.server"
        ) from err
    return _decode(result)


async def list_tools_async() -> list[dict]:
    async with Client(_target()) as client:
        listed = await client.list_tools()
    return [{"name": t.name, "description": t.description} for t in listed.tools]


def _run(coro):
    """Run a coroutine from sync code, even if an event loop is already running (e.g. Streamlit)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def worker():
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as err:  # noqa: BLE001
            box["error"] = err

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict:
    return _run(call_tool_async(name, arguments))


def list_tools() -> list[dict]:
    return _run(list_tools_async())

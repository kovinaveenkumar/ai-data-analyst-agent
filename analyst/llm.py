"""Claude wrapper.

Every agent needs structured output (e.g. {"sql": ..., "reasoning": ...}). We ask the API
for a reply that must match a JSON schema (structured outputs). If a model does not support
that, we fall back to a tool whose input schema is the output we want. Token usage is
recorded for every call so the app can show cost.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from analyst.config import get_settings


@dataclass
class CallRecord:
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    seconds: float


@dataclass
class UsageTracker:
    calls: list[CallRecord] = field(default_factory=list)

    @property
    def input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    def cost_usd(self) -> float | None:
        """Estimated cost, only if prices are configured in .env (see .env.example)."""
        s = get_settings()
        prices = {
            s.main_model: (s.main_input_price, s.main_output_price),
            s.fast_model: (s.fast_input_price, s.fast_output_price),
        }
        total = 0.0
        for c in self.calls:
            p_in, p_out = prices.get(c.model, (None, None))
            if p_in is None or p_out is None:
                return None
            total += (c.input_tokens + c.cache_read_tokens) * p_in / 1e6 + c.output_tokens * p_out / 1e6
        return round(total, 5)


class LLM(Protocol):
    usage: UsageTracker

    def structured(
        self, *, agent: str, fast: bool, system: str, prompt: str, tool_name: str, schema: dict,
        max_tokens: int = 1500,
    ) -> dict: ...


def strict_schema(schema: dict) -> dict:
    """Adapt a JSON schema for structured outputs: every object closed, unsupported keywords removed."""
    if isinstance(schema, dict):
        out = {k: strict_schema(v) for k, v in schema.items() if k not in ("maxItems", "minItems")}
        if out.get("type") == "object":
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [strict_schema(v) for v in schema]
    return schema


def parse_json_text(text: str) -> dict:
    """Pull a JSON object out of a text reply (tolerates code fences or stray words around it)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


class ClaudeLLM:
    """Real Claude client.

    Structured output strategy, tried in order and remembered per model:
      1. "structured" - the API's structured outputs (output_config.format = json_schema).
         The reply is guaranteed to match the schema.
      2. "tool" - give Claude one tool whose input schema is the output and ask it to call it
         (tool_choice "auto", since some newer models do not accept a forced tool choice).
         If it answers in text instead, the JSON is parsed from the text.
    """

    def __init__(self, api_key: str | None = None):
        import anthropic

        settings = get_settings()
        key = api_key or settings.anthropic_api_key
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=key, max_retries=3)
        self.settings = settings
        self.usage = UsageTracker()
        self._mode: dict[str, str] = {}  # model -> "structured" | "tool"

    def _record(self, agent: str, model: str, response, start: float) -> None:
        u = response.usage
        self.usage.calls.append(
            CallRecord(
                agent=agent,
                model=model,
                input_tokens=u.input_tokens or 0,
                output_tokens=u.output_tokens or 0,
                cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                seconds=round(time.perf_counter() - start, 2),
            )
        )

    def structured(self, *, agent, fast, system, prompt, tool_name, schema, max_tokens=1500) -> dict:
        model = self.settings.fast_model if fast else self.settings.main_model
        # system prompt holds the schema: mark it cacheable so repeat calls are cheaper
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        messages = [{"role": "user", "content": prompt}]

        if self._mode.get(model, "structured") == "structured":
            start = time.perf_counter()
            try:
                response = self.client.messages.create(
                    model=model, max_tokens=max_tokens, system=system_blocks, messages=messages,
                    output_config={"format": {"type": "json_schema", "schema": strict_schema(schema)}},
                )
            except self._anthropic.BadRequestError:
                self._mode[model] = "tool"  # this model/account doesn't support it: use the fallback
            else:
                self._mode[model] = "structured"
                self._record(agent, model, response, start)
                text = "".join(b.text for b in response.content if b.type == "text")
                try:
                    return parse_json_text(text)
                except (ValueError, json.JSONDecodeError) as err:
                    raise RuntimeError(f"{agent}: could not read Claude's JSON reply ({err}).") from err

        # fallback: tool use without forcing, then text parsing
        start = time.perf_counter()
        response = self.client.messages.create(
            model=model, max_tokens=max_tokens,
            system=system_blocks + [{"type": "text", "text":
                f"Always answer by calling the {tool_name} tool exactly once. Do not reply in plain text."}],
            tools=[{"name": tool_name, "description": f"Return the {agent} output.", "input_schema": schema}],
            tool_choice={"type": "auto"},
            messages=messages,
        )
        self._record(agent, model, response, start)
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return dict(block.input)
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            return parse_json_text(text)
        except (ValueError, json.JSONDecodeError) as err:
            raise RuntimeError(
                f"{agent}: Claude did not return structured output (stop_reason={response.stop_reason})."
            ) from err


class ScriptedLLM:
    """Test double: returns queued responses per agent, records prompts. No network, no key."""

    def __init__(self, responses: dict[str, list[dict]]):
        self.responses = {k: list(v) for k, v in responses.items()}
        self.prompts: list[tuple[str, str]] = []
        self.usage = UsageTracker()

    def structured(self, *, agent, fast, system, prompt, tool_name, schema, max_tokens=1500) -> dict:
        self.prompts.append((agent, prompt))
        queue = self.responses.get(agent) or []
        if not queue:
            raise AssertionError(f"ScriptedLLM has no response left for agent '{agent}'")
        self.usage.calls.append(CallRecord(agent, "scripted", 100, 50, 0, 0.0))
        return json.loads(json.dumps(queue.pop(0)))  # deep copy


def get_llm() -> LLM:
    return ClaudeLLM()


def preview_rows(result: dict, limit: int = 40) -> str:
    """Compact text version of a query result for prompts (keeps token use low)."""
    rows = result.get("rows", [])[:limit]
    payload: dict[str, Any] = {"columns": result.get("columns", []), "row_count": result.get("row_count", 0),
                               "truncated": result.get("truncated", False), "rows": rows}
    if result.get("row_count", 0) > limit:
        payload["note"] = f"showing first {limit} of {result['row_count']} rows"
    return json.dumps(payload, default=str)

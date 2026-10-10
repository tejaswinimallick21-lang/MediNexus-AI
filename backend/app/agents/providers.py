"""
LLM providers for the Nexa agents. Both run the same loop: the model asks for tools, we execute
them (scoped and audited), feed results back, and stop when it answers. Selection:

    NEXA_LLM_PROVIDER = claude | openai | rules   (optional override)
    otherwise ANTHROPIC_API_KEY -> Claude, else OPENAI_API_KEY -> OpenAI, else the rules engine.
"""

import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.agents.tools import Tool

try:  # the project's .env (gitignored) holds the API keys and wins over older machine-level values
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=True)
except ImportError:  # pragma: no cover
    pass

MAX_STEPS = int(os.getenv("NEXA_MAX_STEPS", "5"))  # tool rounds per question (cost cap)
OPENAI_MAX_TOKENS = int(os.getenv("NEXA_OPENAI_MAX_TOKENS", "700"))  # reply length cap (cost cap)
CLAUDE_MODEL = os.getenv("NEXA_CLAUDE_MODEL", "claude-opus-5-5")
OPENAI_MODEL = os.getenv("NEXA_OPENAI_MODEL", "gpt-4o-mini")

Executor = Callable[[str, Dict[str, Any]], Dict[str, Any]]
Trace = List[Dict[str, Any]]


class ProviderError(Exception):
    """The LLM could not be reached or refused; the engine falls back to the rules engine."""


def active_provider() -> str:
    forced = (os.getenv("NEXA_LLM_PROVIDER") or "").strip().lower()
    if forced in ("claude", "openai", "rules"):
        return forced
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "rules"


def provider_label() -> str:
    p = active_provider()
    return {"claude": f"Claude ({CLAUDE_MODEL}) agents", "openai": f"OpenAI ({OPENAI_MODEL}) agents"}.get(p, "Rules engine (no LLM key)")


def _log(trace: Trace, name: str, args: Dict[str, Any], result: Dict[str, Any]) -> None:
    trace.append({"name": name, "args": args, "ok": bool(result.get("ok")), "error": result.get("error")})


def run_claude(system: str, history: List[Tuple[str, str]], message: str, tools: List[Tool], execute: Executor) -> Tuple[str, Trace]:
    import anthropic

    client = anthropic.Anthropic()
    tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.schema()} for t in tools]
    messages: List[Dict[str, Any]] = []
    for q, a in history:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": message})
    trace: Trace = []
    try:
        for _ in range(MAX_STEPS):
            resp = client.beta.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=16000,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                tools=tool_defs,
                messages=messages,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},  # re-run on a fallback model if a safety classifier declines
            )
            if resp.stop_reason == "refusal":
                raise ProviderError("The model declined this request.")
            calls = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not calls:
                return "\n".join(b.text for b in resp.content if b.type == "text").strip(), trace
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for c in calls:
                r = execute(c.name, dict(c.input or {}))
                _log(trace, c.name, dict(c.input or {}), r)
                results.append({"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(r, default=str), "is_error": not r.get("ok")})
            messages.append({"role": "user", "content": results})  # all results in one message
        return "I stopped after several tool steps without a final answer. Please narrow the question.", trace
    except anthropic.AuthenticationError as e:
        raise ProviderError("The Anthropic API key was rejected.") from e
    except anthropic.RateLimitError as e:
        raise ProviderError("Claude rate limit reached; try again shortly.") from e
    except anthropic.APIStatusError as e:
        raise ProviderError(f"Claude API error {e.status_code}.") from e
    except anthropic.APIConnectionError as e:
        raise ProviderError("Cannot reach the Claude API.") from e


def run_openai(system: str, history: List[Tuple[str, str]], message: str, tools: List[Tool], execute: Executor) -> Tuple[str, Trace]:
    import openai

    client = openai.OpenAI()
    tool_defs = [{"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.schema()}} for t in tools]
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    for q, a in history:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": message})
    trace: Trace = []
    try:
        for _ in range(MAX_STEPS):
            resp = client.chat.completions.create(model=OPENAI_MODEL, messages=messages, tools=tool_defs, temperature=0.1, max_tokens=OPENAI_MAX_TOKENS)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                return (msg.content or "").strip(), trace
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in msg.tool_calls
            ]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args, r = {}, {"ok": False, "error": "Arguments were not valid JSON."}
                else:
                    r = execute(tc.function.name, args)
                _log(trace, tc.function.name, args, r)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(r, default=str)})
        return "I stopped after several tool steps without a final answer. Please narrow the question.", trace
    except openai.AuthenticationError as e:
        raise ProviderError("The OpenAI API key was rejected.") from e
    except openai.RateLimitError as e:
        raise ProviderError("OpenAI quota or rate limit reached (check your credit balance).") from e
    except openai.APIStatusError as e:
        raise ProviderError(f"OpenAI API error {e.status_code}.") from e
    except openai.APIConnectionError as e:
        raise ProviderError("Cannot reach the OpenAI API.") from e


def complete(system: str, prompt: str, max_tokens: int = 160) -> str:
    """One short, tool-free completion (used by the sweep to word a justification). Raises ProviderError."""
    provider = active_provider()
    if provider == "openai":
        import openai

        try:
            resp = openai.OpenAI().chat.completions.create(
                model=OPENAI_MODEL, temperature=0.1, max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            return (resp.choices[0].message.content or "").strip()
        except openai.OpenAIError as e:
            raise ProviderError(f"OpenAI: {type(e).__name__}") from e
    if provider == "claude":
        import anthropic

        try:
            resp = anthropic.Anthropic().messages.create(
                model=CLAUDE_MODEL, max_tokens=max(max_tokens, 1024), system=system, output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
            )
            if resp.stop_reason == "refusal":
                raise ProviderError("The model declined.")
            return "\n".join(b.text for b in resp.content if b.type == "text").strip()
        except anthropic.AnthropicError as e:
            raise ProviderError(f"Claude: {type(e).__name__}") from e
    raise ProviderError("No LLM configured.")

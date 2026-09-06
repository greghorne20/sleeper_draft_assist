#!/usr/bin/env python3
"""The one place that talks to Microsoft Agent Framework.

Everything else in this package is plain Python: `brief.py` decides what is true,
`tools.py` reads files. This module is the seam, and it is deliberately thin --
build an agent, run one prompt, validate what comes back, retry once.

WHY THE IMPORTS ARE LAZY
    `agent-framework` is an optional extra. `sleeper-warroom --dry-run` builds
    prompts and writes nothing, and that has to work on a machine where the extra
    was never installed -- including the draft-day machine, where the whole point
    is that the board does not depend on this layer.

WHY ONE AGENT PER POLL, NOT PER ROOM
    A run with no session is stateless, and the tools are bound to the board and
    the available set, which are the same for all twelve seats at a given pick.
    So one agent is built per poll and twelve prompts run against it concurrently.

WHY THE RETRY FEEDS THE PROBLEMS BACK
    `validate_brief` already names exactly what is wrong in the words a reader
    would use. Handing that back is a better second attempt than asking again.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from ..client import SleeperError
from .brief import Brief, validate_brief

INSTRUCTIONS = Path(__file__).parent / "INSTRUCTIONS.md"

# The brief is short, but tool calls add turns before it is written.
DEFAULT_MAX_TOKENS = 8000

# Claude 5 family. Overridable with --model or ANTHROPIC_CHAT_MODEL.
DEFAULT_MODEL = "claude-sonnet-5"


def load_instructions(playbook: Path) -> str:
    """The war-room framing plus this league's doctrine, as one system prompt.

    PLAYBOOK.md goes here rather than in each prompt because every brief needs
    all of it and it does not change during a draft -- it is the part worth
    keeping stable across twelve concurrent calls.
    """
    if not INSTRUCTIONS.exists():
        raise SleeperError(f"War-room instructions are missing from the package: {INSTRUCTIONS}")
    text = INSTRUCTIONS.read_text()
    if playbook.exists():
        text += "\n\n---\n\n# PLAYBOOK.md — the doctrine you draft by\n\n" + playbook.read_text()
    return text


def build_agent(instructions: str, tools: list[Callable[..., str]], model: str,
                max_tokens: int = DEFAULT_MAX_TOKENS) -> Any:
    """An Agent Framework agent over Anthropic, with this poll's tools bound."""
    try:
        from agent_framework import Agent
        from agent_framework.anthropic import AnthropicClient
    except ImportError as exc:  # pragma: no cover - depends on the optional extra
        raise SleeperError(
            "The war room needs the optional agent-framework extra. Install it with "
            "`uv sync --extra warroom`, or run with --dry-run to build prompts only."
        ) from exc

    return Agent(
        client=AnthropicClient(model=model),
        name="WarRoom",
        instructions=instructions,
        tools=tools,
        default_options={"max_tokens": max_tokens},
    )


def _usage(result: Any) -> dict:
    """Token counts if the provider reported them. Never fatal -- it is telemetry."""
    for attr in ("usage_details", "usage"):
        raw = getattr(result, attr, None)
        if raw is None:
            continue
        if isinstance(raw, dict):
            return {k: v for k, v in raw.items() if isinstance(v, int)}
        return {name: getattr(raw, name) for name in
                ("input_token_count", "output_token_count", "input_tokens", "output_tokens")
                if isinstance(getattr(raw, name, None), int)}
    return {}


def _rejection_note(problems: list[str]) -> str:
    return ("\n\n## Your previous attempt was rejected\n\n"
            "It was checked against the board and these are the problems:\n\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\n\nWrite the brief again, fixing every one. Take player_ids and names together "
              "from the available rows above or from `board_rows`; do not carry over a name you "
              "remember. This is the last attempt before the previous brief is kept instead.")


async def generate_brief(agent: Any, prompt: str, available: dict[str, dict],
                         retries: int = 1) -> tuple[Brief | None, list[str], dict]:
    """One room's brief, validated. Returns (brief, problems, usage).

    A brief is only returned when it passes `validate_brief`, so a caller can
    never render an unvalidated recommendation. When every attempt fails the
    problems come back instead and the caller keeps the previous brief.
    """
    attempt = prompt
    problems: list[str] = []
    usage: dict = {}

    for _ in range(retries + 1):
        result = await agent.run(attempt, options={"response_format": Brief})
        usage = _usage(result)
        brief = getattr(result, "value", None)
        if not isinstance(brief, Brief):
            problems = [f"the model did not return a brief matching the schema: "
                        f"{str(getattr(result, 'text', result))[:200]}"]
        else:
            problems = validate_brief(brief, available)
            if not problems:
                return brief, [], usage
        attempt = prompt + _rejection_note(problems)

    return None, problems, usage


async def generate_with_timeout(agent: Any, prompt: str, available: dict[str, dict],
                                timeout_s: float) -> tuple[Brief | None, list[str], dict, float]:
    """As above, bounded. A brief that arrives after the pick is worth nothing."""
    import asyncio

    started = time.monotonic()
    try:
        brief, problems, usage = await asyncio.wait_for(
            generate_brief(agent, prompt, available), timeout=timeout_s)
    except asyncio.TimeoutError:
        return None, [f"timed out after {timeout_s:.0f}s"], {}, time.monotonic() - started
    except Exception as exc:  # noqa: BLE001 - one room must not take the others down
        return None, [f"{type(exc).__name__}: {exc}"], {}, time.monotonic() - started
    return brief, problems, usage, time.monotonic() - started

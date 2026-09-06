#!/usr/bin/env python3
"""Watch the draft state and keep twelve war-room briefs current.

    uv run sleeper-warroom --once              # one cycle against the current state
    uv run sleeper-warroom --watch             # keep going until the draft ends
    uv run sleeper-warroom --once --dry-run    # build prompts, call nothing

WHAT THIS PROCESS IS, AND IS NOT
    It is strictly additive. `sleeper-live` owns the Sleeper API and writes
    draft/state/; this reads what it wrote and writes briefs alongside. It makes
    no Sleeper requests of its own, holds no lock, and shares nothing with the
    poller or the server but the filesystem. Kill it mid-draft and the board is
    untouched -- the page loses one panel and everything else keeps working.

WHICH ROOMS REGENERATE
    Not all twelve on every pick. `brief.refresh_targets` asks the narrower
    question -- for whom did the answer actually change? -- because a brief
    written for a team forty picks out is work nobody reads. `--refresh all`
    forces every seat every pick.

WHAT A FAILURE DOES
    Keeps the previous brief and marks it. A room that times out or errors never
    blanks its panel, never blocks the other eleven, and never stops the loop.

WHAT IT COSTS, MEASURED
    One room against the real 208-player board: ~33k input and ~5k output tokens,
    ~70 seconds. Most of the input is the agentic loop, not the prompt -- every
    tool result re-sends the conversation, so a brief that reads three research
    notes pays for the system prompt four times.

    Agent Framework's Anthropic provider sets no cache_control breakpoints, so
    none of that is cached today (`usage` in briefs.json reports
    cache_read_input_tokens: 0). The 17.6KB of instructions plus PLAYBOOK is
    identical across all twelve rooms and every poll, so this is the obvious
    place to optimise if the bill matters -- it needs the raw Anthropic client
    passed in via AnthropicClient(anthropic_client=...).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from ..client import SleeperError
from ..live import load_json, team_state, write_atomic
from . import brief as B
from .agent import DEFAULT_MODEL, build_agent, generate_with_timeout, load_instructions
from .tools import build_tools

# How many rooms may be generating at once. Twelve concurrent calls is fine for
# the API and miserable to read in a log.
CONCURRENCY = 6

# A brief that arrives after the pick it was written for is worth nothing -- but
# measured against the real board, one room with tool calls takes ~70s, so this
# is generous on purpose. Too tight and every room fails at once.
TIMEOUT_S = 120.0

# How often to look for a new pick. The poller writes every ~10s; this is cheap
# because it is one stat() until picks_made actually moves.
WATCH_INTERVAL_S = 2.0

TERMINAL_STATUSES = ("complete", "completed")


def load_env_file(path: Path) -> list[str]:
    """Read KEY=VALUE lines into the environment. Returns the names it set.

    Agent Framework does not read a .env itself, and `--model` wants to default
    from one, so this runs before the arguments are parsed. Written by hand
    rather than pulling python-dotenv: --dry-run has to work on a machine where
    the optional extra was never installed, and this is ten lines.

    Anything already exported wins, so a real environment variable is never
    silently overridden by a stale file.
    """
    if not path.exists():
        return []
    names = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            names.append(key)
    return names


def parse_args() -> argparse.Namespace:
    loaded = load_env_file(Path(os.environ.get("SLEEPER_ENV_FILE", ".env")))
    if loaded:
        print(f"loaded {', '.join(sorted(loaded))} from .env", file=sys.stderr)

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state-dir", type=Path, default=Path("draft/state"),
                   help="Where sleeper-live writes state.json (default draft/state)")
    p.add_argument("--board", type=Path, default=Path("draft/board.json"))
    p.add_argument("--playbook", type=Path, default=Path("draft/PLAYBOOK.md"))
    p.add_argument("--model", default=os.environ.get("ANTHROPIC_CHAT_MODEL", DEFAULT_MODEL),
                   help=f"Anthropic model (or ANTHROPIC_CHAT_MODEL; default {DEFAULT_MODEL})")
    p.add_argument("--refresh", choices=("hot", "all"), default="hot",
                   help="hot: only rooms this pick invalidated (default). all: every seat, "
                        "every pick -- roughly four times the cost.")
    p.add_argument("--slot", type=int, default=None,
                   help="Generate only this seat. Useful for trying a prompt change cheaply.")
    p.add_argument("--hot-within", type=int, default=B.HOT_WITHIN,
                   help=f"Picks from its turn a room counts as hot (default {B.HOT_WITHIN})")
    p.add_argument("--cold-every", type=int, default=B.COLD_EVERY,
                   help=f"Refresh an idle room this often (default {B.COLD_EVERY})")
    p.add_argument("--timeout", type=float, default=TIMEOUT_S)
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument("--watch", action="store_true", help="Keep going until the draft completes")
    p.add_argument("--interval", type=float, default=WATCH_INTERVAL_S,
                   help=f"Seconds between state checks (default {WATCH_INTERVAL_S})")
    p.add_argument("--once", action="store_true", help="One cycle, then stop (the default)")
    p.add_argument("--dry-run", action="store_true",
                   help="Write the prompts to <state-dir>/prompts/ and call no model")
    args = p.parse_args()
    if args.concurrency < 1:
        p.error("--concurrency must be >= 1")
    if args.slot is not None and args.slot < 1:
        p.error("--slot is 1-based")
    return args


def load_briefs(path: Path) -> dict:
    """The previous cycle's briefs, or an empty document.

    A missing or corrupt file is not an error: briefs are regenerable, and
    refusing to start because the last write was interrupted would be the wrong
    trade during a draft.
    """
    if not path.exists():
        return {"rooms": {}}
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"warning: {path} is not valid JSON; starting from empty briefs", file=sys.stderr)
        return {"rooms": {}}
    return raw if isinstance(raw, dict) and isinstance(raw.get("rooms"), dict) else {"rooms": {}}


def write_briefs(briefs: dict, state_dir: Path) -> Path:
    """briefs.json for the page, briefs.md for reading, one file per seat.

    Atomic, through the same helper the state uses -- serve.py reads these with
    no coordination, so a truncated read is the failure to design out.
    """
    path = state_dir / "briefs.json"
    write_atomic(path, json.dumps(briefs, indent=1) + "\n")
    write_atomic(state_dir / "briefs.md", B.render_briefs_md(briefs))
    teams = state_dir / "teams"
    teams.mkdir(parents=True, exist_ok=True)
    for key, room in (briefs.get("rooms") or {}).items():
        write_atomic(teams / f"BRIEF-slot-{key}.md", B.render_brief_md(room))
    return path


async def run_cycle(all_state: dict, board: dict, briefs: dict, args: argparse.Namespace) -> dict:
    """One pass: pick the rooms that need work, generate them, merge the rest."""
    available = B.available_index(board, all_state)
    targets = B.refresh_targets(all_state, briefs, args.hot_within, args.cold_every,
                                mode=args.refresh)
    if args.slot is not None:
        targets &= {args.slot}

    rooms = dict(briefs.get("rooms") or {})
    picks_made = all_state.get("picks_made")

    if not targets:
        print(f"pick {picks_made}: nothing to regenerate", file=sys.stderr)
        return {**briefs, "picks_made": picks_made, "rooms": rooms}

    ordered = sorted(targets)
    print(f"pick {picks_made}: regenerating {len(ordered)} room(s): "
          + ", ".join(str(s) for s in ordered), file=sys.stderr)

    if args.dry_run:
        out = args.state_dir / "prompts"
        out.mkdir(parents=True, exist_ok=True)
        for slot in ordered:
            seat = team_state(all_state, slot)
            prompt = B.build_prompt(seat, all_state, rooms.get(str(slot)))
            write_atomic(out / f"slot-{slot}.md", prompt)
            print(f"  slot {slot}: {len(prompt)} chars -> {out}/slot-{slot}.md", file=sys.stderr)
        return {**briefs, "picks_made": picks_made, "rooms": rooms}

    agent = build_agent(load_instructions(args.playbook),
                        build_tools(board, available), args.model)
    gate = asyncio.Semaphore(args.concurrency)

    async def one(slot: int) -> tuple[int, dict]:
        seat = team_state(all_state, slot)
        previous = rooms.get(str(slot))
        prompt = B.build_prompt(seat, all_state, previous)
        async with gate:
            written, problems, usage, took = await generate_with_timeout(
                agent, prompt, available, args.timeout)
        if written is None:
            why = "; ".join(problems) or "unknown"
            print(f"  slot {slot}: FAILED after {took:.1f}s -- {why}", file=sys.stderr)
            if previous:
                kept = dict(previous)
                kept["status"] = "error"
                kept["error"] = why
                return slot, kept
            return slot, B.new_room(seat, all_state, None, model=args.model,
                                    status="error", error=why)
        print(f"  slot {slot}: {written.pick.name} ({written.pick.pos}) in {took:.1f}s",
              file=sys.stderr)
        return slot, B.new_room(seat, all_state, written, model=args.model,
                                usage=usage, available=available)

    for slot, room in await asyncio.gather(*(one(s) for s in ordered)):
        rooms[str(slot)] = room

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "picks_made": picks_made,
        "current_pick": all_state.get("current_pick"),
        "model": args.model,
        "rooms": rooms,
    }


async def run(args: argparse.Namespace) -> int:
    state_path = args.state_dir / "state.json"
    board = load_json(args.board, "Board")
    if not board.get("players"):
        raise SleeperError(f"Board {args.board} has no players. Run `uv run sleeper-board` first.")

    briefs_path = args.state_dir / "briefs.json"
    seen: int | None = None

    while True:
        if not state_path.exists():
            if not args.watch:
                raise SleeperError(
                    f"{state_path} does not exist. Start `uv run sleeper-live --watch` first; "
                    "this process reads what the poller writes and never calls Sleeper itself."
                )
            print(f"waiting for {state_path}...", file=sys.stderr)
            await asyncio.sleep(args.interval)
            continue

        all_state = load_json(state_path, "Draft state")
        picks_made = all_state.get("picks_made")

        if picks_made != seen:
            seen = picks_made
            briefs = await run_cycle(all_state, board, load_briefs(briefs_path), args)
            write_briefs(briefs, args.state_dir)

        if not args.watch:
            break
        if (all_state.get("status") or "").lower() in TERMINAL_STATUSES:
            print("draft complete -- stopping", file=sys.stderr)
            break
        await asyncio.sleep(args.interval)

    print(f"wrote {briefs_path} and {args.state_dir}/briefs.md", file=sys.stderr)
    return 0


def main() -> int:
    return asyncio.run(run(parse_args()))


def cli() -> None:
    """Console-script entry point. Turns SleeperError into exit code 1."""
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        sys.exit(130)
    except SleeperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()

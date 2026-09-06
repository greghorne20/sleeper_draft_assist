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

WHICH MODEL WRITES WHICH BRIEF
    Rooms within --hot-within picks of their turn get --model; everything else
    gets --cold-model. Over a full draft that is 574 hot and 444 cold, and the
    cold ones are planning notes nobody is reading closely. The brief you
    actually act on is always the better model's: a room that close to its turn
    regenerates on every single pick, so by the time you are on the clock yours
    has been rewritten several times over.

WHAT IT COSTS, MEASURED
    Per warm brief, one room, real board:

        sonnet  in 11,200  read 17,900  out 2,900   ~$0.0825
        haiku   in 15,115  read 14,418  out   928   ~$0.0212

    Simulated across all 156 picks with the real pick order and the real trigger:

        one model, no cache                        1,018 gens   ~$152
        one model, cached                          1,018 gens   ~$84
        hot/cold split, cached (the default)   574 + 444 gens   ~$57

    Two things drive this and neither is the prompt. Most of the input is the
    agentic loop -- every tool result re-sends the conversation, so a brief that
    reads three notes pays for the system prompt four times, which is exactly why
    caching a byte-identical prefix pays. And output is over half of a Sonnet
    brief's cost, which caching cannot touch; that is what the cold model is for.

    The count is sensitive to what the briefs recommend. A brief whose proposal
    gets drafted regenerates that room, so if briefs mostly name players who go
    immediately the trigger degenerates towards --refresh all (1,884 gens).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from ..client import SleeperError
from ..live import load_json, team_state, write_atomic
from . import brief as B
from .agent import (
    DEFAULT_COLD_MODEL,
    DEFAULT_MODEL,
    build_agent,
    generate_with_timeout,
    load_instructions,
)
from .tools import build_tools

# How many rooms may be generating at once. Twelve concurrent calls is fine for
# the API and miserable to read in a log. Eight is the number that keeps a
# typical refresh to one wave -- at the current triggers a pick invalidates ~6.7
# rooms, and a gate below that turns one 70s cycle into two.
CONCURRENCY = 8

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
    p.add_argument("--cold-model",
                   default=os.environ.get("ANTHROPIC_COLD_MODEL", DEFAULT_COLD_MODEL),
                   help=f"Model for rooms nowhere near their turn (or ANTHROPIC_COLD_MODEL; "
                        f"default {DEFAULT_COLD_MODEL}). Set it equal to --model to use one "
                        f"model for everything.")
    p.add_argument("--refresh", choices=("hot", "all"), default="hot",
                   help="hot: only rooms this pick invalidated (default). all: every seat, "
                        "every pick -- roughly four times the cost.")
    p.add_argument("--slot", type=int, default=None,
                   help="Generate only this seat. Useful for trying a prompt change cheaply.")
    p.add_argument("--hot-within", type=int, default=B.HOT_WITHIN,
                   help=f"Picks from its turn a room counts as hot (default {B.HOT_WITHIN})")
    p.add_argument("--cold-every", type=int, default=B.COLD_EVERY,
                   help=f"Refresh an idle room this often (default {B.COLD_EVERY})")
    p.add_argument("--no-cache", action="store_true",
                   help="Do not attach cache_control to the system prompt. The prefix is "
                        "identical across all twelve rooms and every poll, so caching is "
                        "normally a large win; this exists to measure it.")
    p.add_argument("--cache-ttl", default="1h", choices=("5m", "1h"),
                   help="Prompt-cache lifetime (default 1h). 5m is Anthropic's default but "
                        "this league's pick timer is 300s, so a slow pick can expire the "
                        "prefix exactly when the next brief needs it.")
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


def write_briefs_json(briefs: dict, state_dir: Path) -> Path:
    """Just the file the page polls, so a finished room is visible immediately.

    Called after every room completes rather than once per cycle. A first cycle
    regenerates all twelve and takes over a minute; waiting for the slowest would
    404 the endpoint for that whole time, and a restart inside the window would
    throw away every room that had already finished.
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / "briefs.json"
    write_atomic(path, json.dumps(briefs, indent=1) + "\n")
    return path


def write_briefs(briefs: dict, state_dir: Path) -> Path:
    """The JSON plus the markdown, at the end of a cycle.

    Atomic, through the same helper the state uses -- serve.py reads these with
    no coordination, so a truncated read is the failure to design out. The
    markdown is written once per cycle rather than per room: nothing polls it,
    and rendering thirteen files after every completion is waste.
    """
    path = write_briefs_json(briefs, state_dir)
    write_atomic(state_dir / "briefs.md", B.render_briefs_md(briefs))
    teams = state_dir / "teams"
    teams.mkdir(parents=True, exist_ok=True)
    for key, room in (briefs.get("rooms") or {}).items():
        write_atomic(teams / f"BRIEF-slot-{key}.md", B.render_brief_md(room))
    return path


def refresh_order(targets: set[int], warm: set[int]) -> list[int]:
    """Hot rooms first, then by slot number.

    The semaphore lets `--concurrency` rooms through at a time, so plain slot
    order would put a planning note forty picks out ahead of the room that is on
    the clock -- and the brief anyone acts on is the one that would be waiting.
    """
    return sorted(targets, key=lambda slot: (slot not in warm, slot))


async def run_cycle(all_state: dict, board: dict, briefs: dict, args: argparse.Namespace,
                    persist: Callable[[dict], Any] | None = None) -> dict:
    """One pass: pick the rooms that need work, generate them, merge the rest.

    `persist` is called with the whole document each time a room finishes, so the
    page sees each brief as it lands instead of nothing until the slowest one is
    done.
    """
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

    warm = B.hot_slots(all_state, args.hot_within) & targets
    ordered = refresh_order(targets, warm)
    print(f"pick {picks_made}: regenerating {len(ordered)} room(s) -- "
          f"{len(warm)} near their turn on {args.model}, "
          f"{len(ordered) - len(warm)} on {args.cold_model}", file=sys.stderr)

    if args.dry_run:
        out = args.state_dir / "prompts"
        out.mkdir(parents=True, exist_ok=True)
        for slot in ordered:
            seat = team_state(all_state, slot)
            prompt = B.build_prompt(seat, all_state, rooms.get(str(slot)))
            write_atomic(out / f"slot-{slot}.md", prompt)
            print(f"  slot {slot}: {len(prompt)} chars -> {out}/slot-{slot}.md", file=sys.stderr)
        return {**briefs, "picks_made": picks_made, "rooms": rooms}

    # One agent per model, not per room: a run carries no session, and the tools
    # are bound to this poll's board, which every seat shares.
    instructions = load_instructions(args.playbook)
    tools = build_tools(board, available)
    agents: dict[str, Any] = {}

    def agent_for(model: str) -> Any:
        if model not in agents:
            agents[model] = build_agent(instructions, tools, model,
                                        cache=not args.no_cache, ttl=args.cache_ttl)
        return agents[model]

    # The rooms someone is actually reading get the better model. Most rooms over
    # a draft are nowhere near their turn, and a brief written forty picks out is
    # a planning note -- the cheaper model is the right tool for it. Same
    # definition of "hot" the refresh trigger uses, so the two cannot drift.
    hot = B.hot_slots(all_state, args.hot_within) if args.cold_model != args.model else set(ordered)
    gate = asyncio.Semaphore(args.concurrency)

    async def one(slot: int) -> tuple[int, dict]:
        model = args.model if slot in hot else args.cold_model
        seat = team_state(all_state, slot)
        previous = rooms.get(str(slot))
        prompt = B.build_prompt(seat, all_state, previous)
        async with gate:
            written, problems, usage, took = await generate_with_timeout(
                agent_for(model), prompt, available, args.timeout)
        if written is None:
            why = "; ".join(problems) or "unknown"
            print(f"  slot {slot} [{model}]: FAILED after {took:.1f}s -- {why}", file=sys.stderr)
            if previous:
                kept = dict(previous)
                kept["status"] = "error"
                kept["error"] = why
                return slot, kept
            return slot, B.new_room(seat, all_state, None, model=model,
                                    status="error", error=why)
        print(f"  slot {slot} [{model}]: {written.pick.name} ({written.pick.pos}) "
              f"in {took:.1f}s", file=sys.stderr)
        return slot, B.new_room(seat, all_state, written, model=model,
                                usage=usage, available=available)

    def document() -> dict:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "picks_made": picks_made,
            "current_pick": all_state.get("current_pick"),
            "model": args.model,
            "rooms": rooms,
        }

    # as_completed rather than gather: a room that finishes in 13 seconds should
    # not wait on one that takes 70.
    for finished in asyncio.as_completed([one(s) for s in ordered]):
        slot, room = await finished
        rooms[str(slot)] = room
        if persist is not None:
            persist(document())

    return document()


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
            # The endpoint should exist as soon as this process does, so a 404
            # means "no war room", not "the war room is still on its first cycle".
            if not briefs_path.exists():
                write_briefs_json({"rooms": {}, "picks_made": picks_made}, args.state_dir)
            briefs = await run_cycle(
                all_state, board, load_briefs(briefs_path), args,
                persist=lambda doc: write_briefs_json(doc, args.state_dir))
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

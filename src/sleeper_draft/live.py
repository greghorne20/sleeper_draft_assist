#!/usr/bin/env python3
"""Poll the live draft and write the current state the assistant reads.

    uv run sleeper-live                     # one shot
    uv run sleeper-live --watch             # poll until the draft completes
    uv run sleeper-live --watch --interval 5

Writes two files, overwritten every poll:

    draft/state/NOW.md      what is true right now, in reading order
    draft/state/state.json  the same, machine-readable

INPUTS
    Everything except the picks comes from the artifacts sleeper-board already
    built: draft/board.json supplies rank, tier, ADP, flags and scouting for a
    player_id, and draft/pick_order.json supplies the third-round-reversal pick
    numbers. Only /draft/<id>/picks is fetched, so a poll is one small request.

WHOSE TEAM IS MINE
    Sleeper's draft object carries draft_order (user_id -> slot) once the draft
    is set up. --slot states it outright; --username resolves it through that
    map. Without one of them there is no "my next pick", so the pick-timing
    math -- which is most of the value here -- is skipped rather than guessed.

OFF-BOARD PICKS
    The board ranks 208 players and 156 picks get made, but nothing stops a
    rival drafting someone unranked. Those picks are recorded from Sleeper's
    own pick metadata and listed separately; they are not an error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from threading import Event

from .board import market_adp
from .client import SleeperClient, SleeperError

# Starting slots this league fills, and what FLEX accepts. Read from the league
# config carried in board.json rather than hardcoded, but FLEX eligibility is a
# Sleeper constant.
FLEX_POSITIONS = ("RB", "WR", "TE")

# How many recent picks to scan when deciding whether a position is running.
RUN_WINDOW = 12

# PLAYBOOK D3: a player is at risk if their ADP is within this many picks of
# the pick you have to survive until.
DEFAULT_CUSHION = 4

TERMINAL_STATUSES = ("complete", "completed")


def _env_int(name: str) -> int | None:
    """An int from the environment, or None. A hosting platform injects PORT as a
    string and an unparseable one should say so rather than silently falling back
    to a port nobody is routing to."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise SleeperError(f"{name}={raw!r} is not an integer") from None


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--draft-id", default=None,
                   help="Draft to poll. Default: draft_id from the board's league config.")
    p.add_argument("--board", type=Path, default=Path("draft/board.json"))
    p.add_argument("--pick-order", type=Path, default=Path("draft/pick_order.json"))
    p.add_argument("--out-dir", type=Path, default=Path("draft/state"))
    p.add_argument("--slot", type=int, default=_env_int("SLEEPER_SLOT"),
                   help="My draft slot (1-based, or SLEEPER_SLOT). Overrides --username. "
                        "Only sets which seat NOW.md and the page open on -- all twelve are "
                        "written either way.")
    p.add_argument("--username", default=os.environ.get("SLEEPER_USERNAME"),
                   help="Resolve my slot through the draft order (or set SLEEPER_USERNAME)")
    p.add_argument("--cushion", type=int, default=DEFAULT_CUSHION,
                   help=f"ADP cushion for the at-risk list (default {DEFAULT_CUSHION})")
    p.add_argument("--available", type=int, default=30,
                   help="How many available players to list (default 30)")
    p.add_argument("--watch", action="store_true", help="Poll until the draft completes")
    p.add_argument("--interval", type=float, default=10.0,
                   help="Seconds between polls when --watch (default 10)")
    p.add_argument("--serve", action="store_true",
                   help="Also serve a live HTML view of the state")
    p.add_argument("--port", type=int, default=_env_int("PORT") or 8765,
                   help="Port for --serve (default 8765, or $PORT -- which is what a host "
                        "like Railway injects)")
    p.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                   help="Bind address for --serve (default 127.0.0.1, or $HOST). 0.0.0.0 puts "
                        "your at-risk list and roster plan on the network -- not something to "
                        "hand a rival at the table, and the deliberate setting inside a "
                        "container where the platform edge is the front door.")
    p.add_argument("--cache-dir", default=None, help="Override the players cache directory")
    args = p.parse_args()
    if args.interval < 1:
        p.error("--interval must be >= 1 second; Sleeper is a shared public API")
    if args.slot is not None and args.slot < 1:
        p.error("--slot is 1-based")
    if args.cushion < 0:
        p.error("--cushion must be >= 0")
    return args


def load_json(path: Path, what: str) -> dict:
    if not path.exists():
        raise SleeperError(f"{what} {path} does not exist. Run `uv run sleeper-board` first.")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SleeperError(f"{what} {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SleeperError(f"{what} {path} must be a JSON object, got {type(raw).__name__}")
    return raw


def load_board(path: Path) -> dict:
    board = load_json(path, "Board")
    if not isinstance(board.get("players"), list) or not board["players"]:
        raise SleeperError(f"Board {path} has no non-empty 'players' list")
    if not isinstance(board.get("league"), dict):
        raise SleeperError(f"Board {path} has no 'league' block; regenerate it with sleeper-board")
    return board


def load_pick_order(path: Path) -> dict:
    order = load_json(path, "Pick order")
    for field in ("picks_by_slot", "slot_by_pick"):
        if not isinstance(order.get(field), dict) or not order[field]:
            raise SleeperError(f"Pick order {path} has no non-empty '{field}'")
    return order


def resolve_slot(draft: dict, order: dict, slot: int | None, username: str | None,
                 client: SleeperClient) -> tuple[int | None, str]:
    """My draft slot, and a one-line account of where it came from."""
    slots = order["picks_by_slot"]
    if slot is not None:
        if str(slot) not in slots:
            raise SleeperError(
                f"--slot {slot} is not one of the {len(slots)} slots in this draft "
                f"({', '.join(sorted(slots, key=int))})."
            )
        return slot, f"--slot {slot}"
    if not username:
        return None, "not set -- pass --slot or --username for pick timing"

    draft_order = draft.get("draft_order")
    if not isinstance(draft_order, dict) or not draft_order:
        raise SleeperError(
            f"Draft {draft.get('draft_id')} has no draft_order yet, so --username cannot be "
            "resolved to a slot. Sleeper populates it when the draft board is set. Pass "
            "--slot directly, or wait until the order is drawn."
        )
    user = client.get_user(username)
    user_id = user.get("user_id")
    resolved = draft_order.get(str(user_id))
    if resolved is None:
        raise SleeperError(
            f"User {username!r} (user_id {user_id}) is not in this draft's draft_order. "
            f"It lists {len(draft_order)} user(s). Pass --slot if you are drafting for "
            "someone else."
        )
    return int(resolved), f"--username {username} -> slot {resolved}"


def pick_player_name(pick: dict) -> str:
    """A display name for a pick, from Sleeper's own pick metadata."""
    meta = pick.get("metadata") or {}
    first = (meta.get("first_name") or "").strip()
    last = (meta.get("last_name") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    return str(pick.get("player_id") or "unknown")


# What a live view of a player actually shows. Everything else on a board row --
# sleeper_name, tier_pos, composite_score, research_note and friends -- exists for
# the board or for the join, and would only widen the contract a renderer binds to.
DISPLAY_FIELDS = ("player_id", "rank", "pos_rank", "pos", "name", "team", "bye", "tier",
                  "value_vs_market", "risk_flag", "sleeper_injury_status", "flags",
                  "handcuff_for_name", "scouting", "note")


def display_row(row: dict) -> dict:
    """A board row narrowed to what a live view shows, with ADP flattened.

    NOW.md and state.json both render from this, so the two outputs cannot drift:
    anything the markdown shows has to survive the projection.
    """
    out = {field: row[field] for field in DISPLAY_FIELDS
           if row.get(field) not in (None, [], "")}
    adp = market_adp(row)
    if adp is not None:
        out["adp"] = adp
    return out


def roster_needs(roster: list[dict], roster_positions: list[str]) -> dict:
    """Which starting slots are still empty, filling FLEX last.

    Greedy and deliberately simple: a drafted player fills a dedicated slot at
    his position if one is open, otherwise FLEX, otherwise bench. That matches
    how you actually read a roster mid-draft.
    """
    required: dict[str, int] = {}
    flex_slots = 0
    for slot in roster_positions or []:
        if slot == "BN":
            continue
        if slot == "FLEX":
            flex_slots += 1
        else:
            required[slot] = required.get(slot, 0) + 1

    counts: dict[str, int] = {}
    for player in roster:
        counts[player["pos"]] = counts.get(player["pos"], 0) + 1

    filled = {pos: min(counts.get(pos, 0), need) for pos, need in required.items()}
    spare = sum(counts.get(pos, 0) - filled.get(pos, 0)
                for pos in set(counts) | set(required)
                if pos in FLEX_POSITIONS)
    flex_filled = min(spare, flex_slots)

    needs = [pos for pos, need in required.items() if filled.get(pos, 0) < need]
    return {
        "required": required,
        "counts": counts,
        "starters_filled": filled,
        "flex_slots": flex_slots,
        "flex_filled": flex_filled,
        "open_starters": needs,
        "flex_open": flex_filled < flex_slots,
        "bench_used": max(0, len(roster) - sum(filled.values()) - flex_filled),
    }


# --- the state, in two halves --------------------------------------------
#
# Everything below `summarize_league` is true of the draft no matter whose seat
# you read it from; everything in `slot_view` depends on the seat and nothing
# else does. That split is the whole reason twelve war rooms cost the same two
# HTTP requests as one: the expensive half runs once per poll.

LEAGUE_ONLY_FIELDS = ("war_rooms", "rosters_by_slot", "default_slot")


def team_label(state: dict, slot: object) -> str:
    """What to call a seat. The slot number is the only identity Sleeper
    guarantees, but a name is what anyone at the table actually says."""
    if slot is None:
        return "an unknown seat"
    return (state.get("team_names") or {}).get(str(slot)) or f"slot {slot}"


def summarize_league(board: dict, order: dict, draft: dict, picks: list[dict],
                     available_limit: int, team_names: dict[int, str] | None = None,
                     seating_provisional: bool = False) -> dict:
    """The seat-independent half of the state. Pure, so it tests without HTTP.

    Keepers arrive here as ordinary picks carrying `is_keeper`, at the pick
    number their round cost implies, so they leave the board through the same
    path as everything else and need no special case.
    """
    rows = {row["player_id"]: row for row in board["players"]}
    league = board["league"]
    teams = int(order["teams"])
    rounds = int(order["rounds"])
    total_picks = teams * rounds

    drafted: dict[str, dict] = {}
    off_board: list[dict] = []
    by_roster: dict[str, list[dict]] = {}
    history: list[dict] = []

    for pick in sorted(picks, key=lambda p: p.get("pick_no") or 0):
        pid = str(pick.get("player_id") or "")
        pick_no = pick.get("pick_no")
        row = rows.get(pid)
        entry = {
            "pick_no": pick_no,
            "round": pick.get("round"),
            "draft_slot": pick.get("draft_slot"),
            "roster_id": pick.get("roster_id"),
            "player_id": pid,
            "name": (row or {}).get("name") or pick_player_name(pick),
            "pos": (row or {}).get("pos") or (pick.get("metadata") or {}).get("position"),
            "team": (row or {}).get("team") or (pick.get("metadata") or {}).get("team"),
            "rank": (row or {}).get("rank"),
            "tier": (row or {}).get("tier"),
            "bye": (row or {}).get("bye"),
            "on_board": row is not None,
            "is_keeper": bool(pick.get("is_keeper")),
        }
        history.append(entry)
        if pid:
            drafted[pid] = entry
        if row is None:
            off_board.append(entry)
        slot = entry["draft_slot"]
        if isinstance(slot, int):
            # Keyed by string so the map survives a JSON round-trip unchanged --
            # the page reads this file back and would otherwise see "7" != 7.
            by_roster.setdefault(str(slot), []).append(entry)

    picks_made = len(history)
    current_pick = picks_made + 1 if picks_made < total_picks else None
    current_round = ((current_pick - 1) // teams + 1) if current_pick else None
    on_the_clock = order["slot_by_pick"].get(str(current_pick)) if current_pick else None

    available = [row for row in board["players"] if row["player_id"] not in drafted]
    shown = [display_row(row) for row in available[:available_limit]]

    tier_status: dict[str, dict[str, int]] = {}
    for row in available:
        tier_status.setdefault(row["pos"], {})
        key = str(row["tier"])
        tier_status[row["pos"]][key] = tier_status[row["pos"]].get(key, 0) + 1

    recent = history[-RUN_WINDOW:]
    run: dict[str, int] = {}
    for entry in recent:
        if entry["pos"]:
            run[entry["pos"]] = run.get(entry["pos"], 0) + 1

    # Resolved for every seat up front, fallbacks included, so no renderer has
    # to carry its own "or slot N" branch.
    named = {key: (team_names or {}).get(int(key)) or f"Slot {key}"
             for key in order["picks_by_slot"]}

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "draft_id": draft.get("draft_id"),
        "status": draft.get("status"),
        "league_name": league.get("league_name"),
        "teams": teams,
        "rounds": rounds,
        "roster_positions": league.get("roster_positions") or [],
        "team_names": named,
        "seating_provisional": seating_provisional,
        "total_picks": total_picks,
        "picks_made": picks_made,
        "picks_remaining": total_picks - picks_made,
        "current_pick": current_pick,
        "current_round": current_round,
        "on_the_clock_slot": on_the_clock,
        "available_count": len(available),
        "best_available": shown,
        "tier_status": tier_status,
        "recent_picks": recent,
        "position_run": run,
        "off_board_picks": off_board,
        "drafted_count": len(drafted),
        "rosters_by_slot": by_roster,
    }


def slot_view(league: dict, order: dict, slot: int | None, cushion: int) -> dict:
    """One seat's read on the shared state: timing, roster, and what is leaving.

    Urgency comes back as `leaving_ids` rather than a flag on each row because
    the board is shared across twelve seats and duplicating thirty rows apiece
    to carry one boolean is the wrong trade. `flatten` puts it back on the row
    for rendering, so "urgency is a property of a player, not a second board"
    still holds everywhere it is read.
    """
    current_pick = league["current_pick"]
    my_picks = [int(n) for n in order["picks_by_slot"].get(str(slot), [])] if slot else []
    upcoming = [n for n in my_picks if current_pick and n >= current_pick]
    my_next = upcoming[0] if upcoming else None
    my_after_next = upcoming[1] if len(upcoming) > 1 else None
    is_my_turn = bool(my_next and current_pick and my_next == current_pick)

    # The pick a player must survive until to still be there for me. On the
    # clock that is my following pick; otherwise it is this one.
    horizon = my_after_next if is_my_turn else my_next
    # How many picks OTHER teams make between now and the horizon. On the clock I
    # consume current_pick myself, so it is not one of theirs; waiting, it is.
    # PLAYBOOK D3 states the on-the-clock form (next - current - 1); the waiting
    # form is one larger because current_pick has not been used up yet.
    picks_before_horizon = (
        horizon - current_pick - (1 if is_my_turn else 0)
    ) if (horizon and current_pick) else None

    my_roster = league["rosters_by_slot"].get(str(slot), []) if slot else []
    needs = roster_needs(my_roster, league.get("roster_positions") or [])

    bye_counts: dict[str, int] = {}
    for player in my_roster:
        if player["bye"] is not None:
            key = str(player["bye"])
            bye_counts[key] = bye_counts.get(key, 0) + 1

    threshold = (horizon + cushion) if horizon is not None else None
    leaving_ids = [] if threshold is None else [
        row["player_id"] for row in league["best_available"]
        if row.get("adp") is not None and row["adp"] <= threshold
    ]

    return {
        "my_slot": slot,
        "is_my_turn": is_my_turn,
        "my_picks": my_picks,
        "my_next_pick": my_next,
        "my_pick_after_next": my_after_next,
        "survive_until_pick": horizon,
        "picks_before_horizon": picks_before_horizon,
        "my_roster": my_roster,
        "roster": needs,
        "bye_counts": bye_counts,
        "leaving_ids": leaving_ids,
        "leaving_count": len(leaving_ids),
    }


def flatten(league: dict, view: dict, cushion: int) -> dict:
    """Merge one seat's view onto the shared state -- the flat shape NOW.md renders.

    Both `summarize` and `team_state` end here, so the merge that could drift
    between the one-seat and twelve-seat paths has a single implementation.
    """
    out = {key: value for key, value in league.items() if key not in LEAGUE_ONLY_FIELDS}
    if view["survive_until_pick"] is not None:
        ids = set(view["leaving_ids"])
        out["best_available"] = [{**row, "leaving": row["player_id"] in ids}
                                 for row in league["best_available"]]
    out["cushion"] = cushion
    out.update({key: value for key, value in view.items()
                if key not in ("leaving_ids", "name")})
    if view.get("name"):
        out["my_team_name"] = view["name"]
    return out


def empty_view(league: dict) -> dict:
    """The no-seat view: timing skipped rather than guessed, as it always was."""
    return {
        "my_slot": None, "is_my_turn": False, "my_picks": [], "my_next_pick": None,
        "my_pick_after_next": None, "survive_until_pick": None,
        "picks_before_horizon": None, "my_roster": [],
        "roster": roster_needs([], league.get("roster_positions") or []),
        "bye_counts": {}, "leaving_ids": [], "leaving_count": 0,
    }


def summarize_all(board: dict, order: dict, draft: dict, picks: list[dict],
                  cushion: int, available_limit: int,
                  team_names: dict[int, str] | None = None,
                  default_slot: int | None = None,
                  seating_provisional: bool = False) -> dict:
    """The whole league: shared state once, plus one war room per draft slot.

    `default_slot` is only which seat a reader should open on -- the operator's
    own. It is deliberately not part of any seat's state, so a war room reads
    the same whoever is looking at it.
    """
    league = summarize_league(board, order, draft, picks, available_limit, team_names,
                              seating_provisional)
    war_rooms = {}
    for key in sorted(order["picks_by_slot"], key=int):
        view = slot_view(league, order, int(key), cushion)
        view["name"] = league["team_names"][key]
        war_rooms[key] = view
    return {**league, "cushion": cushion, "default_slot": default_slot,
            "war_rooms": war_rooms}


def team_state(all_state: dict, slot: int | None) -> dict:
    """Flatten the twelve-seat state down to one seat.

    This is what `summarize` returns, projected out of the league state rather
    than computed again, so a NOW.md written for slot 7 and the slot-7 block in
    state.json cannot disagree.
    """
    view = (all_state.get("war_rooms") or {}).get(str(slot)) if slot else None
    return flatten(all_state, view or empty_view(all_state), all_state["cushion"])


def summarize(board: dict, order: dict, draft: dict, picks: list[dict],
              my_slot: int | None, cushion: int, available_limit: int,
              team_names: dict[int, str] | None = None) -> dict:
    """One seat's whole state. The shape `render_now_md` and the tests expect."""
    league = summarize_league(board, order, draft, picks, available_limit, team_names)
    view = slot_view(league, order, my_slot, cushion) if my_slot else empty_view(league)
    return flatten(league, view, cushion)


def _flags(row: dict) -> str:
    bits = []
    if row.get("risk_flag"):
        bits.append(f"**⚠ {row['risk_flag']}**")
    if row.get("sleeper_injury_status"):
        bits.append(f"{row['sleeper_injury_status']}")
    if row.get("flags"):
        bits.append(" ".join(f"`{flag}`" for flag in row["flags"]))
    if row.get("handcuff_for_name"):
        bits.append(f"✂️ for {row['handcuff_for_name']}")
    if row.get("scouting"):
        bits.append(row["scouting"])
    return " · ".join(bits)


def _player_table(rows: list[dict], horizon: int | None) -> list[str]:
    """One board. The `Gone?` column is the urgency layer, not a second table."""
    gone = f"Gone by {horizon}?" if horizon else "Gone?"
    out = [f"| # | Pos | Player | Tm | Bye | id | ADP | {gone} | Notes |",
           "|---:|---|---|---|---:|---|---:|---|---|"]
    for row in rows:
        adp = row.get("adp")
        leaving = "**YES**" if row.get("leaving") else ""
        out.append(
            f"| {row['rank']} | {row['pos_rank']} | {row['name']} | {row['team']} | "
            f"{row['bye']} | {row['player_id']} | {'-' if adp is None else adp} | "
            f"{leaving} | {_flags(row)} |"
        )
    return out


def render_now_md(state: dict) -> str:
    out: list[str] = []
    seat = state.get("my_team_name") or (
        team_label(state, state["my_slot"]) if state.get("my_slot") else None)
    title = f"# Draft state — {state.get('league_name') or 'league'}"
    out.append(f"{title} — {seat}" if seat else title)
    out.append("")
    out.append(f"_{state['generated_at']} · regenerated every poll · "
               f"doctrine: `draft/PLAYBOOK.md` · full board: `draft/board.md`_")
    out.append("")
    if state.get("seating_provisional"):
        out.append("> **⚠ Seating is provisional.** The draft order is not drawn yet, so team "
                   "names are matched by roster id. The names are real; which one sits in "
                   "which slot is not settled.")
        out.append("")

    if state["current_pick"] is None:
        out.append(f"## Draft complete — all {state['total_picks']} picks are in.")
        out.append("")
    else:
        turn = "**YOUR PICK — you are on the clock.**" if state["is_my_turn"] else (
            f"On the clock: {team_label(state, state['on_the_clock_slot'])}."
        )
        out.append(f"## Pick {state['current_pick']} of {state['total_picks']} "
                   f"(round {state['current_round']}) — {turn}")
        out.append("")
        out.append(f"- {state['picks_made']} picks made, {state['picks_remaining']} remaining.")
        if state["my_slot"]:
            out.append(f"- Me: **{team_label(state, state['my_slot'])}** "
                       f"(slot {state['my_slot']}) · my picks: "
                       + ", ".join(str(n) for n in state["my_picks"]))
            if state["my_next_pick"]:
                out.append(f"- My next pick: **{state['my_next_pick']}**"
                           + (f", then {state['my_pick_after_next']}"
                              if state["my_pick_after_next"] else " (last one)"))
            if state["survive_until_pick"]:
                out.append(f"- **{state['picks_before_horizon']} picks by other teams** before "
                           f"pick {state['survive_until_pick']} comes back to me.")
        else:
            out.append("- My slot is not set, so pick-timing and the at-risk list are off. "
                       "Pass `--slot N` or `--username`.")
        out.append("")

    # --- my roster ---
    if state["my_slot"]:
        roster = state["roster"]
        out.append("## My roster")
        out.append("")
        if not state["my_roster"]:
            out.append("Nothing drafted yet.")
        else:
            out.append("| Pick | Rd | Player | Pos | Tm | Bye | Tier |")
            out.append("|---:|---:|---|---|---|---:|---:|")
            for player in state["my_roster"]:
                out.append(f"| {player['pick_no']} | {player['round']} | {player['name']} | "
                           f"{player['pos']} | {player['team']} | {player['bye'] or '-'} | "
                           f"{player['tier'] or '-'} |")
        out.append("")
        counts = " · ".join(f"{pos} {n}" for pos, n in sorted(roster["counts"].items())) or "empty"
        out.append(f"**Have:** {counts}")
        gaps = roster["open_starters"] + (["FLEX"] if roster["flex_open"] else [])
        open_slots = ", ".join(gaps) if gaps else "none — all starters filled"
        out.append(f"**Starting slots still open:** {open_slots}")
        byes = state["bye_counts"]
        heavy = sorted((week for week, n in byes.items() if n >= 3), key=int)
        if heavy:
            stacked = ", ".join(f"week {week} ({byes[week]} players)" for week in heavy)
            out.append(f"**⚠ Bye stack:** {stacked} — PLAYBOOK caps this at 2 "
                       "projected starters per bye week.")
        out.append("")

    # --- the board, with urgency marked on the row ---
    horizon = state["survive_until_pick"]
    out.append(f"## Best available ({state['available_count']} left on the board)")
    out.append("")
    if horizon:
        out.append(f"**{state['leaving_count']} of the {len(state['best_available'])} below are "
                   f"gone before pick {horizon}** — market ADP within {state['cushion']} of it. "
                   "PLAYBOOK D1: take the highest player marked YES over one who will still be "
                   "there.")
    else:
        out.append("No slot set, so nothing can be marked as leaving.")
    out.append("")
    out.extend(_player_table(state["best_available"], horizon))
    out.append("")

    # --- tier status ---
    out.append("## Tiers remaining")
    out.append("")
    out.append("How many available at each position and tier. PLAYBOOK D2: take the last man in "
               "a tier when the count drops to the number of drafters picking before you return.")
    out.append("")
    for pos in ("RB", "WR", "TE", "QB"):
        tiers = state["tier_status"].get(pos)
        if not tiers:
            continue
        out.append(f"- **{pos}** — " + " · ".join(
            f"T{tier} {tiers[tier]}" for tier in sorted(tiers, key=int)))
    out.append("")

    # --- runs and recent picks ---
    if state["recent_picks"]:
        out.append("## Last picks")
        out.append("")
        run = " · ".join(f"{pos} {n}" for pos, n in
                         sorted(state["position_run"].items(), key=lambda kv: -kv[1]))
        out.append(f"Position run over the last {len(state['recent_picks'])} picks: {run}")
        out.append("")
        for entry in reversed(state["recent_picks"]):
            # "you" rather than my own team name, which `← me` would only repeat.
            who = ("**you**" if entry["draft_slot"] == state["my_slot"]
                   else team_label(state, entry["draft_slot"]))
            rank = f"#{entry['rank']}" if entry["rank"] else "unranked"
            kept = " _(keeper)_" if entry.get("is_keeper") else ""
            out.append(f"- `{entry['pick_no']}` {who}: "
                       f"{entry['name']} ({entry['pos']}, {rank}){kept}")
        out.append("")

    if state["off_board_picks"]:
        out.append("## Off-board picks")
        out.append("")
        out.append(f"{len(state['off_board_picks'])} player(s) drafted who are not on our board:")
        for entry in state["off_board_picks"]:
            out.append(f"- `{entry['pick_no']}` {entry['name']} "
                       f"({entry['pos'] or '?'}, {entry['team'] or '?'})")
        out.append("")
    return "\n".join(out)


def write_atomic(path: Path, text: str) -> None:
    """Write through a temp file and rename, so a reader never sees half a file.

    `write_text` truncates and then writes, and serve.py reads the same path with
    no coordination between them -- a page refresh landing inside that window
    gets partial JSON, fails to parse it and reports the poller as unreachable,
    which during a draft is an alarm on the one thing that has to be trusted.
    os.replace is atomic on POSIX, so a reader gets the old file or the new one.

    Deliberately no fsync. This state is derived and rewritten every poll, so
    durability across a power cut buys nothing that the next poll would not
    rebuild, and thirteen fsyncs every ten seconds is real I/O to spend on it.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_state(state: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "state.json"
    md_path = out_dir / "NOW.md"
    write_atomic(json_path, json.dumps(state, indent=1) + "\n")
    write_atomic(md_path, render_now_md(state))
    return md_path, json_path


def write_all_state(all_state: dict, out_dir: Path, my_slot: int | None) -> tuple[Path, Path]:
    """state.json for the league, NOW.md for my seat, one file per other seat.

    NOW.md keeps meaning "my team" at its old path, which is what lets the
    draft-day skill go on reading it unchanged while the league view develops
    alongside. The other eleven land under teams/ so nothing has to guess which
    file is the one it wants.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "state.json"
    md_path = out_dir / "NOW.md"
    write_atomic(json_path, json.dumps(all_state, indent=1) + "\n")
    write_atomic(md_path, render_now_md(team_state(all_state, my_slot)))

    teams_dir = out_dir / "teams"
    teams_dir.mkdir(parents=True, exist_ok=True)
    for key in all_state.get("war_rooms") or {}:
        if my_slot is not None and int(key) == my_slot:
            continue
        write_atomic(teams_dir / f"NOW-slot-{key}.md",
                     render_now_md(team_state(all_state, int(key))))
    return md_path, json_path


def resolve_team_names(client: SleeperClient, league_id: str | None,
                       draft: dict) -> tuple[dict[int, str], str]:
    """slot -> team name, and one line on how sure we are of the seating.

    Two chains, and which one answered matters enough to report:

    - `draft_order` (user_id -> slot) is authoritative, and Sleeper populates it
      when the order is drawn.
    - Before the draw it is null, but `slot_to_roster_id` is already there. Going
      slot -> roster_id -> owner_id -> name gets twelve names out of it, except
      that pre-draft that map is the identity, so the names are right for the
      rosters and *provisional* for the seats.

    A rival's name on the wrong seat is worse than a numbered seat, so the
    provisional case says so rather than passing a guess off as the draw.
    Resolved once at startup; nothing here runs per poll.
    """
    if not league_id:
        return {}, "no league id, so seats are numbered"
    try:
        users = client.get_league_users(str(league_id))
    except SleeperError:
        return {}, "league users unavailable, so seats are numbered"

    by_user: dict[str, str] = {}
    for user in users:
        meta = user.get("metadata") or {}
        # Sleeper stores whatever was typed in, trailing spaces included.
        name = (meta.get("team_name") or user.get("display_name") or "").strip()
        if name:
            by_user[str(user.get("user_id"))] = name

    draft_order = draft.get("draft_order")
    if isinstance(draft_order, dict) and draft_order:
        drawn = {int(slot): by_user[uid]
                 for uid, slot in draft_order.items() if uid in by_user}
        return drawn, f"{len(drawn)} named from the drawn draft order"

    slots = draft.get("slot_to_roster_id")
    if not isinstance(slots, dict) or not slots:
        return {}, "draft order not drawn and no roster map, so seats are numbered"
    try:
        rosters = client.get_rosters(str(league_id))
    except SleeperError:
        return {}, "rosters unavailable, so seats are numbered"

    owner_of = {roster.get("roster_id"): str(roster.get("owner_id"))
                for roster in rosters}
    provisional: dict[int, str] = {}
    for slot, roster_id in slots.items():
        owner = owner_of.get(roster_id)
        if owner in by_user:
            provisional[int(slot)] = by_user[owner]
    return provisional, (f"{len(provisional)} named via roster ids -- PROVISIONAL, "
                         "the draft order is not drawn yet")


def poll_once(client: SleeperClient, draft_id: str, board: dict, order: dict,
              my_slot: int | None, args: argparse.Namespace,
              team_names: dict[int, str] | None = None,
              seating_provisional: bool = False) -> dict:
    draft = client.get_draft(draft_id)
    picks = client.get_draft_picks(draft_id)
    all_state = summarize_all(board, order, draft, picks, args.cushion, args.available,
                              team_names, my_slot, seating_provisional)
    write_all_state(all_state, args.out_dir, my_slot)
    return team_state(all_state, my_slot)


def main() -> int:
    args = parse_args()
    board = load_board(args.board)
    order = load_pick_order(args.pick_order)

    draft_id = args.draft_id or board["league"].get("draft_id")
    if not draft_id:
        raise SleeperError(
            "No draft id: pass --draft-id, or regenerate the board from a config.yaml that "
            "has one (`uv run sleeper-discover`)."
        )

    client = SleeperClient(**({"cache_dir": args.cache_dir} if args.cache_dir else {}))
    draft = client.get_draft(str(draft_id))
    my_slot, provenance = resolve_slot(draft, order, args.slot, args.username, client)
    team_names, naming = resolve_team_names(client, board["league"].get("league_id"), draft)
    provisional = "PROVISIONAL" in naming
    print(f"draft {draft_id} ({draft.get('status')}) · my slot: {provenance} · {naming}",
          file=sys.stderr)

    if args.serve:
        from .serve import serve_in_background

        args.out_dir.mkdir(parents=True, exist_ok=True)
        server = serve_in_background(args.out_dir, args.host, args.port)
        shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
        print(f"serving http://{shown}:{server.server_address[1]}  (Ctrl-C to stop)",
              file=sys.stderr)
        if args.host == "0.0.0.0":  # noqa: S104 - deliberate, and warned about
            print("  WARNING: bound to all interfaces -- anyone on this network can read "
                  "your board, roster plan and at-risk list", file=sys.stderr)

    last_seen = -1
    while True:
        state = poll_once(client, str(draft_id), board, order, my_slot, args,
                          team_names, provisional)
        if state["picks_made"] != last_seen:
            last_seen = state["picks_made"]
            where = (f"pick {state['current_pick']} "
                     f"({team_label(state, state['on_the_clock_slot'])})"
                     if state["current_pick"] else "complete")
            mine = " -- YOUR PICK" if state["is_my_turn"] else ""
            print(f"{state['picks_made']}/{state['total_picks']} picks · {where}{mine}",
                  file=sys.stderr)
        if not args.watch:
            break
        if (state["status"] or "").lower() in TERMINAL_STATUSES or state["current_pick"] is None:
            print("draft complete -- stopping", file=sys.stderr)
            break
        time.sleep(args.interval)

    print(f"wrote {args.out_dir}/NOW.md, {args.out_dir}/state.json and "
          f"{args.out_dir}/teams/ ({len(order['picks_by_slot'])} war rooms)",
          file=sys.stderr)

    if args.serve:
        # Polling is done -- the draft finished, or this was a one-shot run --
        # but the page should stay up so it can still be read.
        print("polling stopped; still serving the page. Ctrl-C to stop.", file=sys.stderr)
        Event().wait()
    return 0


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

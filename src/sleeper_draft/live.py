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


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--draft-id", default=None,
                   help="Draft to poll. Default: draft_id from the board's league config.")
    p.add_argument("--board", type=Path, default=Path("draft/board.json"))
    p.add_argument("--pick-order", type=Path, default=Path("draft/pick_order.json"))
    p.add_argument("--out-dir", type=Path, default=Path("draft/state"))
    p.add_argument("--slot", type=int, default=None,
                   help="My draft slot (1-based). Overrides --username.")
    p.add_argument("--username", default=os.environ.get("SLEEPER_USERNAME"),
                   help="Resolve my slot through the draft order (or set SLEEPER_USERNAME)")
    p.add_argument("--cushion", type=int, default=DEFAULT_CUSHION,
                   help=f"ADP cushion for the at-risk list (default {DEFAULT_CUSHION})")
    p.add_argument("--available", type=int, default=30,
                   help="How many available players to list (default 30)")
    p.add_argument("--watch", action="store_true", help="Poll until the draft completes")
    p.add_argument("--interval", type=float, default=10.0,
                   help="Seconds between polls when --watch (default 10)")
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


def market_adp(row: dict) -> float | None:
    """The market's own read on a player, for the at-risk maths."""
    adp = (row.get("source_ranks") or {}).get("ffc_halfppr_12team_adp")
    if isinstance(adp, (int, float)) and not isinstance(adp, bool):
        return float(adp)
    return None


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


def summarize(board: dict, order: dict, draft: dict, picks: list[dict],
              my_slot: int | None, cushion: int, available_limit: int) -> dict:
    """The whole state, computed from data already in hand. No I/O, so testable."""
    rows = {row["player_id"]: row for row in board["players"]}
    league = board["league"]
    teams = int(order["teams"])
    rounds = int(order["rounds"])
    total_picks = teams * rounds

    drafted: dict[str, dict] = {}
    off_board: list[dict] = []
    by_roster: dict[int, list[dict]] = {}
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
        }
        history.append(entry)
        if pid:
            drafted[pid] = entry
        if row is None:
            off_board.append(entry)
        slot = entry["draft_slot"]
        if isinstance(slot, int):
            by_roster.setdefault(slot, []).append(entry)

    picks_made = len(history)
    current_pick = picks_made + 1 if picks_made < total_picks else None
    current_round = ((current_pick - 1) // teams + 1) if current_pick else None
    on_the_clock = order["slot_by_pick"].get(str(current_pick)) if current_pick else None

    # --- my picks and the two horizons that drive every timing decision ---
    my_picks = [int(n) for n in order["picks_by_slot"].get(str(my_slot), [])] if my_slot else []
    upcoming = [n for n in my_picks if current_pick and n >= current_pick]
    my_next = upcoming[0] if upcoming else None
    my_after_next = upcoming[1] if len(upcoming) > 1 else None
    is_my_turn = bool(my_next and current_pick and my_next == current_pick)

    # The pick a player must survive until to still be there for me. On the
    # clock that is my following pick; otherwise it is this one.
    horizon = my_after_next if is_my_turn else my_next
    picks_before_horizon = (horizon - current_pick - 1) if (horizon and current_pick) else None

    my_roster = by_roster.get(my_slot, []) if my_slot else []
    needs = roster_needs(my_roster, league.get("roster_positions") or [])

    bye_counts: dict[str, int] = {}
    for player in my_roster:
        if player["bye"] is not None:
            key = str(player["bye"])
            bye_counts[key] = bye_counts.get(key, 0) + 1

    # --- the board, minus everyone taken ---
    available = [row for row in board["players"] if row["player_id"] not in drafted]

    at_risk = []
    if horizon is not None:
        threshold = horizon + cushion
        for row in available:
            adp = market_adp(row)
            if adp is not None and adp <= threshold:
                at_risk.append(row)

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

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "draft_id": draft.get("draft_id"),
        "status": draft.get("status"),
        "league_name": league.get("league_name"),
        "teams": teams,
        "rounds": rounds,
        "total_picks": total_picks,
        "picks_made": picks_made,
        "picks_remaining": total_picks - picks_made,
        "current_pick": current_pick,
        "current_round": current_round,
        "on_the_clock_slot": on_the_clock,
        "my_slot": my_slot,
        "is_my_turn": is_my_turn,
        "my_picks": my_picks,
        "my_next_pick": my_next,
        "my_pick_after_next": my_after_next,
        "survive_until_pick": horizon,
        "picks_before_horizon": picks_before_horizon,
        "cushion": cushion,
        "my_roster": my_roster,
        "roster": needs,
        "bye_counts": bye_counts,
        "available_count": len(available),
        "best_available": [display_row(row) for row in available[:available_limit]],
        "at_risk": [display_row(row) for row in at_risk[:available_limit]],
        "tier_status": tier_status,
        "recent_picks": recent,
        "position_run": run,
        "off_board_picks": off_board,
        "drafted_count": len(drafted),
    }


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


def _player_table(rows: list[dict]) -> list[str]:
    out = ["| # | Pos | Player | Tm | Bye | id | ADP | Notes |",
           "|---:|---|---|---|---:|---|---:|---|"]
    for row in rows:
        adp = row.get("adp")
        out.append(
            f"| {row['rank']} | {row['pos_rank']} | {row['name']} | {row['team']} | "
            f"{row['bye']} | {row['player_id']} | {'-' if adp is None else adp} | {_flags(row)} |"
        )
    return out


def render_now_md(state: dict) -> str:
    out: list[str] = []
    out.append(f"# Draft state — {state.get('league_name') or 'league'}")
    out.append("")
    out.append(f"_{state['generated_at']} · regenerated every poll · "
               f"doctrine: `draft/PLAYBOOK.md` · full board: `draft/board.md`_")
    out.append("")

    if state["current_pick"] is None:
        out.append(f"## Draft complete — all {state['total_picks']} picks are in.")
        out.append("")
    else:
        turn = "**YOUR PICK — you are on the clock.**" if state["is_my_turn"] else (
            f"On the clock: slot {state['on_the_clock_slot']}."
        )
        out.append(f"## Pick {state['current_pick']} of {state['total_picks']} "
                   f"(round {state['current_round']}) — {turn}")
        out.append("")
        out.append(f"- {state['picks_made']} picks made, {state['picks_remaining']} remaining.")
        if state["my_slot"]:
            out.append(f"- My slot: **{state['my_slot']}** · my picks: "
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

    # --- at risk ---
    if state["survive_until_pick"] and state["at_risk"]:
        out.append(f"## At risk before pick {state['survive_until_pick']}")
        out.append("")
        out.append(f"Available players whose market ADP is within {state['cushion']} of pick "
                   f"{state['survive_until_pick']}. PLAYBOOK D1: prefer the highest-value player "
                   "here over one who will still be there.")
        out.append("")
        out.extend(_player_table(state["at_risk"]))
        out.append("")

    # --- best available ---
    out.append(f"## Best available ({state['available_count']} left on the board)")
    out.append("")
    out.extend(_player_table(state["best_available"]))
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
            mine = " ← me" if entry["draft_slot"] == state["my_slot"] else ""
            rank = f"#{entry['rank']}" if entry["rank"] else "unranked"
            out.append(f"- `{entry['pick_no']}` slot {entry['draft_slot']}: "
                       f"{entry['name']} ({entry['pos']}, {rank}){mine}")
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


def write_state(state: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "state.json"
    md_path = out_dir / "NOW.md"
    json_path.write_text(json.dumps(state, indent=1) + "\n")
    md_path.write_text(render_now_md(state))
    return md_path, json_path


def poll_once(client: SleeperClient, draft_id: str, board: dict, order: dict,
              my_slot: int | None, args: argparse.Namespace) -> dict:
    draft = client.get_draft(draft_id)
    picks = client.get_draft_picks(draft_id)
    state = summarize(board, order, draft, picks, my_slot, args.cushion, args.available)
    write_state(state, args.out_dir)
    return state


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
    print(f"draft {draft_id} ({draft.get('status')}) · my slot: {provenance}", file=sys.stderr)

    last_seen = -1
    while True:
        state = poll_once(client, str(draft_id), board, order, my_slot, args)
        if state["picks_made"] != last_seen:
            last_seen = state["picks_made"]
            where = (f"pick {state['current_pick']} (slot {state['on_the_clock_slot']})"
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

    print(f"wrote {args.out_dir}/NOW.md and {args.out_dir}/state.json", file=sys.stderr)
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

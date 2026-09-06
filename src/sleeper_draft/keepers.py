#!/usr/bin/env python3
"""Work out who each team may keep, and what the pick costs.

    uv run sleeper-keepers --league-id <2026 league id>
    uv run sleeper-keepers --league-id <id> --season 2025

Writes draft/keepers.md (the report to circulate) and draft/keepers.json.

THE RULES THIS ENCODES
    One keeper per team (Sleeper's own max_keepers confirms it).

    1. Keeping a player forfeits your pick in the round he was drafted in last
       season.
    2. You cannot keep last season's keeper -- one year is the scope, so a
       player kept two seasons ago and re-drafted since is eligible again.
    3. He must have stayed on your roster all season, which here means you
       drafted him and never lost him. A waiver pickup held to the end does not
       qualify, and has no draft round to forfeit anyway.

    So a player is eligible for a team iff all four hold: that team drafted him,
    he is on their final roster, no completed transaction ever dropped him from
    that roster, and he was not last season's keeper.

WHY TRANSACTIONS AND NOT JUST THE FINAL ROSTER
    "On the final roster" and "never left" are different questions: a player
    dropped in week 3 and re-added in week 9 passes the first and fails the
    second. They happened to agree for every 2025 roster, but agreeing once is
    not the same as being the same rule, so this walks the transaction log and
    reports any player where the two answers differ.

TRADES
    Need no special case. Sleeper records the losing side of a trade in `drops`,
    so a player traded away fails the "never left" test, and a player traded for
    fails the "you drafted him" test.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .board import market_adp
from .client import SleeperClient, SleeperError
from .past_draft import walk_back

# Sleeper numbers scoring weeks 1-18; asking for a week that never happened
# returns an empty list rather than an error.
DEFAULT_WEEKS = 18


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league-id", default=os.environ.get("SLEEPER_LEAGUE_ID"),
                   help="This season's league (or set SLEEPER_LEAGUE_ID)")
    p.add_argument("--back", type=int, default=1,
                   help="Seasons to walk back for the source draft (default 1)")
    p.add_argument("--season", default=None,
                   help="Walk back until this season. Overrides --back.")
    p.add_argument("--weeks", type=int, default=DEFAULT_WEEKS,
                   help=f"Scoring weeks of transactions to scan (default {DEFAULT_WEEKS})")
    p.add_argument("--board", type=Path, default=Path("draft/board.json"),
                   help="Optional: this year's board, to show what a keeper is worth now")
    p.add_argument("--out-dir", type=Path, default=Path("draft"))
    p.add_argument("--cache-dir", default=None, help="Override the players cache directory")
    args = p.parse_args()
    if not args.league_id:
        p.error("missing required argument: --league-id")
    if args.season is None and args.back < 1:
        p.error("--back must be >= 1")
    if args.weeks < 1:
        p.error("--weeks must be >= 1")
    return args


def player_label(player_id: str, players: dict[str, dict], pick: dict | None) -> dict:
    """Name / position / team, from the players dump, falling back to the pick.

    Sleeper stamps each pick with its own metadata, so a player who has since
    fallen out of the dump is still nameable from the draft record.
    """
    player = players.get(player_id)
    meta = (pick or {}).get("metadata") or {}
    if isinstance(player, dict):
        name = player.get("full_name") or " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        )
        return {
            "name": name or player_id,
            "pos": player.get("position") or meta.get("position"),
            "nfl_team": player.get("team") or meta.get("team"),
        }
    name = " ".join(part for part in (meta.get("first_name"), meta.get("last_name")) if part)
    return {"name": name.strip() or player_id,
            "pos": meta.get("position"), "nfl_team": meta.get("team")}


def team_label(user: dict | None, roster_id: int) -> dict:
    """What to call a team, and who manages it.

    Sleeper keeps the custom team name in user metadata and it is optional --
    four of the twelve managers in this league have never set one. Fall back to
    the manager's username the way Sleeper's own UI does, then to the roster id,
    so every section of the report has a heading.
    """
    user = user or {}
    manager = user.get("display_name") or user.get("username")
    name = ((user.get("metadata") or {}).get("team_name") or "").strip()
    return {
        "team_name": name or manager or f"roster {roster_id}",
        "display_name": manager,
    }


def dropped_by_roster(transactions: list[dict]) -> dict[int, set[str]]:
    """roster_id -> players a completed transaction moved off that roster.

    Failed and pending waiver claims never moved anyone, so they are ignored.
    """
    dropped: dict[int, set[str]] = {}
    for move in transactions:
        if not isinstance(move, dict) or move.get("status") != "complete":
            continue
        drops = move.get("drops")
        if not isinstance(drops, dict):
            continue
        for player_id, roster_id in drops.items():
            if isinstance(roster_id, int):
                dropped.setdefault(roster_id, set()).add(str(player_id))
    return dropped


def load_board(path: Path) -> dict[str, dict]:
    """This year's board keyed by player_id, or {} if there isn't one.

    Only the public market ADP is taken off it. This report gets circulated to
    the league, and our own rank, tier and scouting are not for sharing.

    Optional by design: keeper eligibility is a fact about last season and does
    not depend on how we rank players now.
    """
    if not path or not path.exists():
        return {}
    try:
        board = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    rows = board.get("players") if isinstance(board, dict) else None
    if not isinstance(rows, list):
        return {}
    return {str(row["player_id"]): row for row in rows
            if isinstance(row, dict) and row.get("player_id")}


def eligible_keepers(picks: list[dict], rosters: list[dict], users: list[dict],
                     transactions: list[dict], players: dict[str, dict],
                     board: dict[str, dict] | None = None) -> dict:
    """The whole ruling, computed from data in hand. No I/O, so testable."""
    board = board or {}
    if not rosters:
        raise SleeperError("The source league returned no rosters, so there is nobody to rule on.")
    if not picks:
        raise SleeperError("The source draft returned no picks, so no keeper can have a round cost.")

    by_user = {str(u["user_id"]): u for u in users
               if isinstance(u, dict) and u.get("user_id")}

    picks_by_roster: dict[int, list[dict]] = {}
    for pick in picks:
        roster_id = pick.get("roster_id")
        if not isinstance(roster_id, int):
            raise SleeperError(
                f"Draft pick {pick.get('pick_no')} has roster_id {roster_id!r}; without it the "
                "pick cannot be attributed to a team."
            )
        picks_by_roster.setdefault(roster_id, []).append(pick)

    dropped = dropped_by_roster(transactions)
    teams = []
    divergences = []

    for roster in sorted(rosters, key=lambda r: r.get("roster_id") or 0):
        roster_id = roster.get("roster_id")
        if not isinstance(roster_id, int):
            raise SleeperError(
                f"Roster owned by {roster.get('owner_id') or '?'} has roster_id "
                f"{roster_id!r}; without it its picks and drops cannot be matched to it."
            )
        final = {str(p) for p in (roster.get("players") or [])}
        left = dropped.get(roster_id, set())
        mine = picks_by_roster.get(roster_id, [])

        eligible, blocked = [], []
        for pick in sorted(mine, key=lambda p: (p.get("round") or 0, p.get("pick_no") or 0)):
            player_id = str(pick.get("player_id") or "")
            if not player_id:
                continue
            label = player_label(player_id, players, pick)
            entry = {
                "player_id": player_id,
                **label,
                "round_cost": pick.get("round"),
                "drafted_at_pick": pick.get("pick_no"),
            }
            row = board.get(player_id)
            if row is not None:
                # Public ADP only -- never our own rank, tier or scouting.
                adp = market_adp(row)
                if adp is not None:
                    entry["adp"] = adp

            if pick.get("is_keeper"):
                blocked.append({**entry, "reason": "kept last season"})
                continue
            # A player on the final roster who was nonetheless dropped at some
            # point is the case the two definitions disagree about. Record it.
            if player_id in final and player_id in left:
                divergences.append({"roster_id": roster_id, **entry,
                                    "note": "on the final roster but was dropped during the season"})
            if player_id not in final:
                continue
            if player_id in left:
                continue
            eligible.append(entry)

        drafted_ids = {str(p.get("player_id")) for p in mine}
        teams.append({
            "roster_id": roster_id,
            "owner_id": roster.get("owner_id"),
            **team_label(by_user.get(str(roster.get("owner_id"))), roster_id),
            "eligible": eligible,
            "blocked": blocked,
            "excluded": {
                "held_but_undrafted": len(final - drafted_ids),
                "drafted_but_left": len(drafted_ids - final),
            },
        })

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "rules": [
            "One keeper per team.",
            "Keeping a player forfeits your pick in the round he was drafted in last season.",
            "Last season's keeper cannot be kept again.",
            "Only players you drafted and never lost are eligible; waiver pickups are not.",
        ],
        "totals": {
            "teams": len(teams),
            "eligible": sum(len(t["eligible"]) for t in teams),
            "blocked": sum(len(t["blocked"]) for t in teams),
            "held_but_undrafted": sum(t["excluded"]["held_but_undrafted"] for t in teams),
        },
        "teams": teams,
        "divergences": divergences,
    }


def render_keepers_md(report: dict, source: dict) -> str:
    out: list[str] = []
    out.append(f"# Keeper eligibility — {source.get('for_league_name') or 'league'} "
               f"({source.get('for_season')} draft)")
    out.append("")
    out.append(f"_Ruled from the {source.get('target_season')} draft, final rosters and "
               f"transaction log. Generated {report['generated_at']}. "
               "**This file is the one to read** — `draft/keepers.json` is the same "
               "ruling for tooling._")
    out.append("")
    out.append("## The rules")
    out.append("")
    for rule in report["rules"]:
        out.append(f"- {rule}")
    out.append("")
    totals = report["totals"]
    out.append(f"**{totals['eligible']} eligible players across {totals['teams']} teams.** "
               f"{totals['blocked']} blocked as last season's keeper; "
               f"{totals['held_but_undrafted']} players were held to the end of the season but "
               "not drafted by their team, so they do not qualify.")
    out.append("")

    for team in report["teams"]:
        out.append(f"## {team['team_name']}")
        out.append("")
        if team["eligible"]:
            has_adp = any("adp" in p for p in team["eligible"])
            header = "| Costs | Player | Pos | Tm | Drafted |"
            divider = "|---|---|---|---|---:|"
            if has_adp:
                header += " 2026 ADP |"
                divider += "---:|"
            out.append(header)
            out.append(divider)
            for player in team["eligible"]:
                row = (f"| **R{player['round_cost']}** | {player['name']} | "
                       f"{player['pos'] or '-'} | {player['nfl_team'] or '-'} | "
                       f"{player['drafted_at_pick']} |")
                if has_adp:
                    adp = player.get("adp")
                    row += f" {adp if adp is not None else '-'} |"
                out.append(row)
        else:
            out.append("_No eligible keepers._")
        out.append("")
        for player in team["blocked"]:
            out.append(f"- **Blocked:** {player['name']} — {player['reason']}.")
        excluded = team["excluded"]
        out.append(f"- Not eligible: {excluded['held_but_undrafted']} held but undrafted, "
                   f"{excluded['drafted_but_left']} drafted but left the roster.")
        out.append("")

    if report["divergences"]:
        out.append("## Dropped and re-acquired")
        out.append("")
        out.append("These players finished the season on the roster that drafted them, but were "
                   "dropped at some point along the way, so they did not stay all year:")
        out.append("")
        for player in report["divergences"]:
            out.append(f"- roster {player['roster_id']}: {player['name']} "
                       f"(drafted R{player['round_cost']})")
        out.append("")
    return "\n".join(out)


def main() -> int:
    args = parse_args()
    client = SleeperClient(**({"cache_dir": args.cache_dir} if args.cache_dir else {}))

    league, chain = walk_back(client, str(args.league_id), args.back, args.season)
    league_id = str(league.get("league_id"))
    walked = " -> ".join(f"{c['season']}:{c['league_id']}" for c in chain)
    print(f"source season {league.get('season')} ({walked})", file=sys.stderr)

    drafts = client.get_league_drafts(league_id)
    if not drafts:
        raise SleeperError(f"League {league_id} (season {league.get('season')}) has no drafts.")
    draft = sorted(drafts, key=lambda d: d.get("created") or 0)[-1]
    picks = client.get_draft_picks(str(draft["draft_id"]))
    rosters = client.get_rosters(league_id)
    users = client.get_league_users(league_id)

    transactions: list[dict] = []
    for week in range(1, args.weeks + 1):
        transactions.extend(client.get_transactions(league_id, week))
    completed = sum(1 for t in transactions if t.get("status") == "complete")
    print(f"{len(picks)} picks · {len(rosters)} rosters · {len(transactions)} transactions "
          f"({completed} completed) over {args.weeks} weeks", file=sys.stderr)

    players = client.get_players()
    board = load_board(args.board)
    if board:
        print(f"enriching with {args.board} ({len(board)} ranked players)", file=sys.stderr)

    report = eligible_keepers(picks, rosters, users, transactions, players, board)
    source = {
        "for_league_id": chain[0]["league_id"],
        "for_league_name": chain[0]["name"],
        "for_season": chain[0]["season"],
        "league_id": league_id,
        "league_name": league.get("name"),
        "target_season": league.get("season"),
        "draft_id": draft.get("draft_id"),
        "chain": chain,
        "weeks_scanned": args.weeks,
    }
    report["source"] = source

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "keepers.json"
    md_path = args.out_dir / "keepers.md"
    json_path.write_text(json.dumps(report, indent=1) + "\n")
    md_path.write_text(render_keepers_md(report, source))

    totals = report["totals"]
    print(f"\nwrote {md_path} and {json_path}", file=sys.stderr)
    print(f"{totals['eligible']} eligible across {totals['teams']} teams · "
          f"{totals['blocked']} blocked as last season's keeper · "
          f"{totals['held_but_undrafted']} held but undrafted", file=sys.stderr)
    for team in report["teams"]:
        print(f"  {team['team_name']:<22} {len(team['eligible']):>2} eligible", file=sys.stderr)
    if report["divergences"]:
        print(f"{len(report['divergences'])} player(s) were dropped and re-acquired -- "
              "listed at the foot of the report", file=sys.stderr)
    return 0


def cli() -> None:
    """Console-script entry point. Turns SleeperError into exit code 1."""
    try:
        sys.exit(main())
    except SleeperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    cli()

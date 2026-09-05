#!/usr/bin/env python3
"""Walk previous_league_id backwards and save a past draft as a JSON fixture.

    python fetch_past_draft.py --league-id 123456789012345678 --back 1
    python fetch_past_draft.py --league-id 123456789012345678 --season 2025
    python fetch_past_draft.py --league-id 123456789012345678 --back 1 --out fixtures/draft_2025.json

The fixture contains the draft settings (rounds, teams, reversal_round if
present, slot_to_roster_id) and the complete picks list, so pick-order maths --
snake with third-round reversal, in particular -- can be checked against a real
board offline.

By default the script insists the draft is complete: pick count must equal
teams * rounds. Pass --allow-partial to save an incomplete draft anyway.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .client import SleeperClient, SleeperError

MAX_CHAIN_HOPS = 30


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--league-id", default=os.environ.get("SLEEPER_LEAGUE_ID"),
                   help="League to start from (or set SLEEPER_LEAGUE_ID)")
    p.add_argument("--back", type=int, default=1,
                   help="How many seasons to walk back via previous_league_id (default 1)")
    p.add_argument("--season", default=None,
                   help="Walk back until this season is reached. Overrides --back.")
    p.add_argument("--draft-id", default=None,
                   help="Specific draft in the target league. Default: most recent.")
    p.add_argument("--out", type=Path, default=None,
                   help="Output path (default fixtures/draft_<season>_<draft_id>.json)")
    p.add_argument("--allow-partial", action="store_true",
                   help="Save even if the pick count does not equal teams * rounds")
    p.add_argument("--cache-dir", default=None, help="Override the players cache directory")
    args = p.parse_args()
    if not args.league_id:
        p.error("missing required argument: --league-id")
    if args.season is None and args.back < 1:
        p.error("--back must be >= 1")
    return args


def walk_back(
    client: SleeperClient, league_id: str, back: int, season: str | None
) -> tuple[dict, list[dict]]:
    """Follow previous_league_id. Returns (target_league, chain_walked)."""
    league = client.get_league(league_id)
    chain = [{"league_id": league.get("league_id"), "season": league.get("season"),
              "name": league.get("name")}]

    if season is not None:
        hops = 0
        while str(league.get("season")) != str(season):
            prev = league.get("previous_league_id")
            if not prev or prev == "0":
                walked = " -> ".join(f"{c['season']}:{c['league_id']}" for c in chain)
                raise SleeperError(
                    f"Chain ended before reaching season {season}. Walked: {walked}"
                )
            hops += 1
            if hops > MAX_CHAIN_HOPS:
                raise SleeperError(
                    f"previous_league_id chain exceeded {MAX_CHAIN_HOPS} hops -- likely a loop."
                )
            league = client.get_league(str(prev))
            chain.append({"league_id": league.get("league_id"), "season": league.get("season"),
                          "name": league.get("name")})
        return league, chain

    for step in range(back):
        prev = league.get("previous_league_id")
        if not prev or prev == "0":
            walked = " -> ".join(f"{c['season']}:{c['league_id']}" for c in chain)
            raise SleeperError(
                f"League {league.get('league_id')} (season {league.get('season')}) has no "
                f"previous_league_id, so it cannot go back {back} season(s) -- got {step}. Walked: {walked}"
            )
        league = client.get_league(str(prev))
        chain.append({"league_id": league.get("league_id"), "season": league.get("season"),
                      "name": league.get("name")})
    return league, chain


def main() -> int:
    args = parse_args()
    client = SleeperClient(**({"cache_dir": args.cache_dir} if args.cache_dir else {}))

    league, chain = walk_back(client, str(args.league_id), args.back, args.season)
    target_league_id = league.get("league_id")
    if not target_league_id:
        raise SleeperError(f"Resolved league object has no 'league_id'. Keys: {sorted(league)}")

    print("chain: " + " -> ".join(f"{c['season']}:{c['league_id']}" for c in chain), file=sys.stderr)

    drafts = client.get_league_drafts(str(target_league_id))
    if not drafts:
        raise SleeperError(f"League {target_league_id} (season {league.get('season')}) has no drafts.")

    if args.draft_id:
        matches = [d for d in drafts if d.get("draft_id") == args.draft_id]
        if not matches:
            raise SleeperError(
                f"Draft {args.draft_id} not found in league {target_league_id}. "
                f"Available: {[d.get('draft_id') for d in drafts]}"
            )
        draft_id = args.draft_id
    else:
        draft_id = drafts[0].get("draft_id")
        if not draft_id:
            raise SleeperError(f"Most recent draft in league {target_league_id} has no 'draft_id'.")

    draft = client.get_draft(str(draft_id))
    picks = client.get_draft_picks(str(draft_id))

    settings = draft.get("settings")
    if not isinstance(settings, dict):
        raise SleeperError(f"Draft {draft_id} has no usable 'settings' object. Keys: {sorted(draft)}")
    for key in ("rounds", "teams"):
        if key not in settings:
            raise SleeperError(f"Draft {draft_id} settings has no '{key}'. Keys: {sorted(settings)}")

    if "slot_to_roster_id" not in draft:
        raise SleeperError(
            f"Draft {draft_id} has no 'slot_to_roster_id' map -- pick-order verification needs it. "
            f"Keys: {sorted(draft)}"
        )

    if not picks:
        raise SleeperError(f"Draft {draft_id} returned zero picks. Nothing to verify against.")

    expected = settings["rounds"] * settings["teams"]
    if len(picks) != expected:
        message = (f"Draft {draft_id} has {len(picks)} picks but rounds*teams = {expected}.")
        if not args.allow_partial:
            raise SleeperError(message + " Pass --allow-partial to save it anyway.")
        print(f"WARNING: {message} Saving anyway (--allow-partial).", file=sys.stderr)

    if "reversal_round" not in settings:
        print(f"NOTE: draft {draft_id} settings has no 'reversal_round' key. "
              f"Keys present: {sorted(settings)}", file=sys.stderr)
    else:
        print(f"reversal_round: {settings['reversal_round']!r}", file=sys.stderr)

    fixture = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "sleeper /league, /league/{id}/drafts, /draft/{id}, /draft/{id}/picks",
        "requested_from_league_id": str(args.league_id),
        "chain": chain,
        "league": {
            "league_id": league.get("league_id"),
            "name": league.get("name"),
            "season": league.get("season"),
            "total_rosters": league.get("total_rosters"),
            "previous_league_id": league.get("previous_league_id"),
            "roster_positions": league.get("roster_positions"),
            "scoring_settings": league.get("scoring_settings"),
        },
        "draft": draft,
        "pick_count": len(picks),
        "expected_pick_count": expected,
        "picks": picks,
    }

    out = args.out or Path("fixtures") / f"draft_{league.get('season')}_{draft_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=2, sort_keys=False))

    print(f"\nwrote {out}", file=sys.stderr)
    print(f"  season {league.get('season')}  draft {draft_id}  type {draft.get('type')!r}  "
          f"{settings['teams']} teams x {settings['rounds']} rounds  {len(picks)} picks", file=sys.stderr)
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

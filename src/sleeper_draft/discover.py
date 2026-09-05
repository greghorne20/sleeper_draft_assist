#!/usr/bin/env python3
"""Resolve a Sleeper username to everything you need to fill in a config file.

Usage:
    python discover.py --username YOUR_NAME --season 2026
    python discover.py --username YOUR_NAME --season 2026 --league-id 123456789012345678

With no --league-id, prints the league list and stops. With one (or when the
season has exactly one league), also prints draft_id, draft settings, the
reversal round, scoring_settings, roster_positions, slot -> roster_id, and
previous_league_id, as a YAML block you can paste into your config.

Nothing is hardcoded: username/season/league come from CLI args or the env vars
SLEEPER_USERNAME, SLEEPER_SEASON, SLEEPER_LEAGUE_ID.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .client import SleeperClient, SleeperError
from .yamlio import dump_yaml

REQUIRED_DRAFT_SETTINGS = ("rounds", "teams")


def require(obj: dict, key: str, where: str):
    """Fetch obj[key] or die naming the missing field. Never defaults."""
    if key not in obj:
        raise SleeperError(f"{where} has no '{key}' field. Keys present: {sorted(obj)}")
    value = obj[key]
    if value is None:
        raise SleeperError(f"{where} has '{key}' set to null, which this script cannot use.")
    return value


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--username", default=os.environ.get("SLEEPER_USERNAME"),
                   help="Sleeper username (or set SLEEPER_USERNAME)")
    p.add_argument("--season", default=os.environ.get("SLEEPER_SEASON"),
                   help="Season, e.g. 2026 (or set SLEEPER_SEASON)")
    p.add_argument("--league-id", default=os.environ.get("SLEEPER_LEAGUE_ID"),
                   help="League to detail (or set SLEEPER_LEAGUE_ID)")
    p.add_argument("--draft-id", default=None,
                   help="Specific draft within the league. Default: the league's most recent draft.")
    p.add_argument("--out", type=Path, default=None,
                   help="Also write the YAML config block to this path.")
    p.add_argument("--cache-dir", default=None, help="Override the players cache directory.")
    args = p.parse_args()

    # A league ID is enough on its own: league -> drafts -> draft needs no user.
    # Without one, we have to go username + season -> league list.
    if not args.league_id:
        missing = [name for name, value in (("--username", args.username), ("--season", args.season))
                   if not value]
        if missing:
            p.error(
                f"missing required argument(s): {', '.join(missing)} "
                "(or pass --league-id to skip user lookup entirely)"
            )
    return args


def main() -> int:
    args = parse_args()
    client = SleeperClient(**({"cache_dir": args.cache_dir} if args.cache_dir else {}))

    user_id = None
    league_id = args.league_id

    if args.username:
        user = client.get_user(args.username)
        user_id = user["user_id"]
        print(f"# user: {user.get('display_name') or args.username}")
        print(f"# user_id: {user_id}\n")

    if not league_id:
        leagues = client.get_user_leagues(user_id, str(args.season))
        if not leagues:
            raise SleeperError(
                f"User {args.username} ({user_id}) has no NFL leagues in season {args.season}."
            )

        print(f"# leagues in {args.season}:")
        for lg in leagues:
            print(
                f"#   {require(lg, 'league_id', 'league')}  "
                f"{lg.get('total_rosters', '?'):>3} teams  "
                f"{lg.get('status', '?'):<12} {lg.get('name', '(unnamed)')}"
            )
        print()

        if len(leagues) == 1:
            league_id = require(leagues[0], "league_id", "league")
            print(f"# only one league this season, auto-selected: {league_id}\n")
        else:
            print("# Re-run with --league-id <id> to print the full config for one league.")
            return 0

    league = client.get_league(str(league_id))
    drafts = client.get_league_drafts(str(league_id))
    if not drafts:
        raise SleeperError(f"League {league_id} has no drafts. Nothing to configure.")

    if args.draft_id:
        matches = [d for d in drafts if d.get("draft_id") == args.draft_id]
        if not matches:
            available = [d.get("draft_id") for d in drafts]
            raise SleeperError(f"Draft {args.draft_id} is not in league {league_id}. Available: {available}")
        draft_stub = matches[0]
    else:
        draft_stub = drafts[0]  # Sleeper returns drafts most-recent first.
        if len(drafts) > 1:
            print(f"# league has {len(drafts)} drafts; using the most recent. "
                  f"Others: {[d.get('draft_id') for d in drafts[1:]]}\n")

    draft = client.get_draft(require(draft_stub, "draft_id", "draft stub"))
    settings = require(draft, "settings", f"draft {draft['draft_id']}")

    for key in REQUIRED_DRAFT_SETTINGS:
        require(settings, key, f"draft {draft['draft_id']} settings")

    slot_to_roster_id = require(draft, "slot_to_roster_id", f"draft {draft['draft_id']}")

    # reversal_round is the field Sleeper uses for third-round reversal. It is not
    # in the public docs, so report exactly what is there rather than assuming.
    reversal_round = settings.get("reversal_round", None)
    if "reversal_round" not in settings:
        print("# NOTE: draft settings contain no 'reversal_round' key.")
        print(f"#       settings keys present: {sorted(settings)}")
        print("#       Set reversal_round manually in your config if the league uses 3RR.\n")
    elif reversal_round in (0, None):
        print(f"# NOTE: reversal_round is {reversal_round!r} -- Sleeper is reporting NO reversal "
              "for this draft.\n")

    config = {
        "user_id": user_id,
        "username": args.username,
        "season": str(args.season) if args.season else league.get("season"),
        "league_id": str(league_id),
        "league_name": league.get("name"),
        "previous_league_id": league.get("previous_league_id"),
        "total_rosters": league.get("total_rosters"),
        "draft_id": draft["draft_id"],
        "draft_type": draft.get("type"),
        "draft_status": draft.get("status"),
        "rounds": settings["rounds"],
        "teams": settings["teams"],
        "reversal_round": reversal_round,
        "draft_settings": dict(settings),
        "slot_to_roster_id": {str(k): v for k, v in slot_to_roster_id.items()},
        "draft_order_user_to_slot": {str(k): v for k, v in (draft.get("draft_order") or {}).items()},
        "roster_positions": require(league, "roster_positions", f"league {league_id}"),
        "scoring_settings": require(league, "scoring_settings", f"league {league_id}"),
    }

    block = dump_yaml(config)
    print("# ---------- paste below into your config ----------")
    print(block, end="")
    print("# ---------- end ----------")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(block)
        print(f"\n# wrote {args.out}", file=sys.stderr)

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

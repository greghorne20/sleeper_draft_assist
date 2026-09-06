#!/usr/bin/env python3
"""Emit the draft research list as chunked YAML files.

Takes the cached Sleeper /players/nfl dump, filters to draftable players,
orders them by draft relevance, and writes fixed-size YAML batches to
research/batches/.

    python build_batches.py --byes byes.2026.json
    python build_batches.py --byes byes.2026.json --limit 220 --chunk-size 35

ORDERING
    Sleeper's player object carries exactly one ordering signal usable for draft
    relevance: `search_rank` (int, lower = more prominent). It is not ADP, but
    it is the only ranking field in the dump. Players with search_rank null or
    the 9999999 sentinel are excluded -- Sleeper uses those for irrelevant or
    placeholder rows. See README for the full field survey.

BYE WEEKS
    The Sleeper player object has NO bye week field. This script therefore
    requires --byes pointing at a JSON map of {"TEAM": week}. If any player's
    team is absent from that map, the script errors and names every missing
    team rather than emitting a null bye.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .client import SleeperClient, SleeperError
from .yamlio import dump_yaml

SEARCH_RANK_SENTINEL = 9999999
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
KDEF_POSITIONS = ("K", "DEF")
VALID_BYE_WEEKS = range(1, 23)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--byes", type=Path, required=True,
                   help='JSON file mapping team abbreviation to bye week, e.g. {"BUF": 12, "KC": 10}')
    p.add_argument("--limit", type=int, default=220,
                   help="How many QB/RB/WR/TE players to include (default 220)")
    p.add_argument("--kickers", type=int, default=12, help="Kickers in the final batch (default 12)")
    p.add_argument("--defenses", type=int, default=12, help="Defenses in the final batch (default 12)")
    p.add_argument("--chunk-size", type=int, default=15, help="Players per YAML file (default 15)")
    p.add_argument("--out-dir", type=Path, default=Path("research/batches"))
    p.add_argument("--refresh-players", action="store_true",
                   help="Force a re-fetch of /players/nfl even if the cache is fresh")
    p.add_argument("--cache-dir", default=None, help="Override the players cache directory")
    args = p.parse_args()
    for name, value in (("--limit", args.limit), ("--chunk-size", args.chunk_size)):
        if value < 1:
            p.error(f"{name} must be >= 1")
    if args.kickers < 0 or args.defenses < 0:
        p.error("--kickers and --defenses must be >= 0")
    return args


def load_byes(path: Path) -> dict[str, int]:
    if not path.exists():
        raise SleeperError(
            f"Bye file {path} does not exist. Sleeper's /players/nfl dump contains no bye week "
            "field, so this script cannot derive byes on its own. Create a JSON map like "
            '{"ARI": 8, "ATL": 5, ...} for all 32 teams.'
        )
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SleeperError(f"Bye file {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SleeperError(f"Bye file {path} must be a JSON object, got {type(raw).__name__}")

    byes: dict[str, int] = {}
    for team, week in raw.items():
        if not isinstance(team, str) or not team:
            raise SleeperError(f"Bye file {path}: team key {team!r} is not a non-empty string")
        if isinstance(week, bool) or not isinstance(week, int):
            raise SleeperError(f"Bye file {path}: bye for {team!r} is {week!r}, expected an integer week")
        if week not in VALID_BYE_WEEKS:
            raise SleeperError(f"Bye file {path}: bye week {week} for {team!r} is outside weeks 1-22")
        byes[team.upper()] = week
    if not byes:
        raise SleeperError(f"Bye file {path} is empty")
    return byes


def player_name(pid: str, player: dict) -> str:
    """Resolve a display name or die naming the player_id."""
    full = player.get("full_name")
    if isinstance(full, str) and full.strip():
        return full.strip()
    first = (player.get("first_name") or "").strip()
    last = (player.get("last_name") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    raise SleeperError(
        f"player_id {pid} has no usable name: full_name={player.get('full_name')!r}, "
        f"first_name={player.get('first_name')!r}, last_name={player.get('last_name')!r}"
    )


def eligible(player: dict, positions: tuple[str, ...]) -> bool:
    """Draftable-and-rostered filter. Anything failing this is not a 'skip' --
    it is a player who cannot be drafted in a redraft league right now."""
    fantasy_positions = player.get("fantasy_positions")
    if not isinstance(fantasy_positions, list):
        return False
    if not any(pos in fantasy_positions for pos in positions):
        return False
    if player.get("active") is not True:
        return False
    if not player.get("team"):
        return False
    # Sleeper never assigns search_rank to team defenses -- every DEF row is null.
    # For every other position the rank exists and is the ordering signal, so keep
    # requiring it there; defenses are kept regardless and sorted by name below.
    if "DEF" in fantasy_positions:
        return True
    rank = player.get("search_rank")
    if not isinstance(rank, int) or isinstance(rank, bool):
        return False
    return rank < SEARCH_RANK_SENTINEL


def rank_key(player: dict) -> int:
    """search_rank for sorting, with null/non-int (e.g. defenses) sent to the end."""
    rank = player.get("search_rank")
    if isinstance(rank, int) and not isinstance(rank, bool):
        return rank
    return SEARCH_RANK_SENTINEL


def select(players: dict[str, dict], positions: tuple[str, ...], limit: int) -> list[tuple[str, dict]]:
    pool = [(pid, p) for pid, p in players.items() if eligible(p, positions)]
    pool.sort(key=lambda item: (
        rank_key(item[1]),
        item[1].get("position") or "",
        (item[1].get("full_name") or item[1].get("last_name") or ""),
        item[0],
    ))
    if len(pool) < limit:
        raise SleeperError(
            f"Only {len(pool)} players matched {positions} after filtering, but {limit} were requested. "
            "Either the players cache is stale/partial or the filters are too strict."
        )
    return pool[:limit]


def primary_position(pid: str, player: dict, positions: tuple[str, ...]) -> str:
    """The position we file this player under, preferring `position` when it is
    one of the requested ones, else the first matching fantasy position."""
    pos = player.get("position")
    if isinstance(pos, str) and pos in positions:
        return pos
    for candidate in player.get("fantasy_positions") or []:
        if candidate in positions:
            return candidate
    raise SleeperError(
        f"player_id {pid} passed the {positions} filter but has no matching position: "
        f"position={player.get('position')!r}, fantasy_positions={player.get('fantasy_positions')!r}"
    )


def to_entries(selection: list[tuple[str, dict]], positions: tuple[str, ...],
               byes: dict[str, int]) -> list[dict]:
    entries: list[dict] = []
    missing_byes: dict[str, list[str]] = {}

    for pid, player in selection:
        team = player["team"]
        if not isinstance(team, str):
            raise SleeperError(f"player_id {pid} has non-string team {team!r}")
        team = team.upper()
        if team not in byes:
            missing_byes.setdefault(team, []).append(player_name(pid, player))
            continue
        entries.append({
            "player_id": str(pid),
            "name": player_name(pid, player),
            "pos": primary_position(pid, player, positions),
            "team": team,
            "bye": byes[team],
            "search_rank": player.get("search_rank"),
        })

    if missing_byes:
        detail = "; ".join(
            f"{team} ({len(names)} players, e.g. {names[0]})" for team, names in sorted(missing_byes.items())
        )
        raise SleeperError(
            f"No bye week in the bye file for {len(missing_byes)} team(s): {detail}. "
            "Add them and re-run. Nothing was written."
        )
    return entries


def write_batches(entries: list[dict], label: str, positions: tuple[str, ...],
                  out_dir: Path, chunk_size: int, start_index: int, total_batches: int) -> list[Path]:
    written = []
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for offset in range(0, len(entries), chunk_size):
        chunk = entries[offset:offset + chunk_size]
        number = start_index + offset // chunk_size
        suffix = f"_{label}" if label else ""
        path = out_dir / f"batch_{number:02d}{suffix}.yaml"
        document = {
            "batch": number,
            "of": total_batches,
            "positions": list(positions),
            "count": len(chunk),
            "ordering": "sleeper search_rank ascending",
            "source": "sleeper /players/nfl",
            "generated_at": generated_at,
            "players": chunk,
        }
        path.write_text(dump_yaml(document))
        written.append(path)
    return written


def main() -> int:
    args = parse_args()
    byes = load_byes(args.byes)

    client = SleeperClient(**({"cache_dir": args.cache_dir} if args.cache_dir else {}))
    age = client.players_cache_age_hours()
    if age is None:
        print("players cache empty -- fetching /players/nfl (~5MB, once per day)", file=sys.stderr)
    elif args.refresh_players:
        print(f"players cache is {age:.1f}h old -- refresh forced", file=sys.stderr)
    else:
        print(f"players cache is {age:.1f}h old -- reusing", file=sys.stderr)
    players = client.get_players(force_refresh=args.refresh_players)
    print(f"players in dump: {len(players)}", file=sys.stderr)

    skill = to_entries(select(players, SKILL_POSITIONS, args.limit), SKILL_POSITIONS, byes)

    kdef: list[dict] = []
    if args.kickers:
        kdef += to_entries(select(players, ("K",), args.kickers), ("K",), byes)
    if args.defenses:
        kdef += to_entries(select(players, ("DEF",), args.defenses), ("DEF",), byes)

    skill_batches = -(-len(skill) // args.chunk_size)
    kdef_batches = -(-len(kdef) // args.chunk_size) if kdef else 0
    total_batches = skill_batches + kdef_batches

    args.out_dir.mkdir(parents=True, exist_ok=True)
    written = write_batches(skill, "", SKILL_POSITIONS, args.out_dir, args.chunk_size, 1, total_batches)
    if kdef:
        written += write_batches(kdef, "k_def", KDEF_POSITIONS, args.out_dir, args.chunk_size,
                                 skill_batches + 1, total_batches)

    by_pos: dict[str, int] = {}
    for entry in skill + kdef:
        by_pos[entry["pos"]] = by_pos.get(entry["pos"], 0) + 1

    print(f"\nwrote {len(written)} files to {args.out_dir}/", file=sys.stderr)
    for path in written:
        print(f"  {path}", file=sys.stderr)
    print(f"\n{len(skill) + len(kdef)} players total: "
          + ", ".join(f"{pos} {count}" for pos, count in sorted(by_pos.items())), file=sys.stderr)
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

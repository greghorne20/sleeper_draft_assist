#!/usr/bin/env python3
"""Build the in-draft board: rankings joined to Sleeper player_ids.

The aggregate rankings in research/ rank players by NAME. Sleeper's live draft
feed identifies picks by PLAYER_ID. Nothing can be crossed off a board that is
keyed by name, so this script performs that join once, offline, and writes the
artifacts the in-draft assistant reads:

    draft/board.json       every ranked player + player_id + research note path
    draft/board.md         the same board, grep-friendly, grouped by tier
    draft/pick_order.json  all slots x rounds, third-round-reversal aware

    uv run sleeper-board

JOIN
    Ranking rows are matched to the cached /players/nfl dump on normalised
    name + fantasy position. A name that matches nothing, or matches more than
    one player the tiebreakers cannot separate, is a hard error naming every
    offender -- a silently dropped ranking row is a player who quietly stops
    existing mid-draft. NAME_ALIASES carries the handful of spelling
    disagreements between the research sources and Sleeper.

SCOUTING
    research/scouting_notes.json carries the qualitative layer -- one short line
    per player, flags (risk/riser/faller/value/handcuff/dead_zone), and the
    handcuff_for links pairing a backup to the starter he backs up. It is keyed
    by player_id, so it is merged straight onto the board rows.

PICK ORDER
    Third-round reversal is undocumented by Sleeper, so the generated table is
    checked against the rankings file's own pick map when one is present. A
    disagreement is an error: two independent derivations of the pick numbers
    must agree before the assistant plans a draft around them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

from .client import SleeperClient, SleeperError

SKILL_POSITIONS = ("QB", "RB", "WR", "TE")

# Ranking-source spelling -> Sleeper spelling, both normalised. Sleeper is the
# authority because its name is what the live pick feed will echo back.
NAME_ALIASES = {
    "nicksingleton": "nicholassingleton",
}

# Sleeper injury designations that change whether a player is draftable at all,
# as opposed to the week-to-week "Questionable" that ~a fifth of the board carries.
SEVERE_INJURY_STATUS = ("IR", "PUP", "NA", "Out", "Doubtful", "Sus")

NOTE_FILENAME = re.compile(r"^(?P<stem>.+)-(?P<pos>[A-Z]{2,3})-(?P<player_id>[A-Za-z0-9]+)\.md$")

RANKING_FIELDS = ("rank", "name", "pos", "team", "bye", "pos_rank", "tier")

# The flag vocabulary scouting_notes.json is allowed to use. A typo'd flag would
# silently never render, so unknown flags are an error rather than a passthrough.
SCOUTING_FLAGS = ("risk", "riser", "faller", "value", "handcuff", "dead_zone")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rankings", type=Path, default=Path("research/rankings_2026.json"),
                   help="Aggregate rankings JSON (default research/rankings_2026.json)")
    p.add_argument("--scouting", type=Path, default=Path("research/scouting_notes.json"),
                   help="Per-player scouting notes keyed by player_id "
                        "(default research/scouting_notes.json)")
    p.add_argument("--notes-dir", type=Path, default=Path("research/players"),
                   help="Per-player research markdown, named <stem>-<POS>-<player_id>.md")
    p.add_argument("--config", type=Path, default=Path("config.yaml"),
                   help="League config from sleeper-discover (default config.yaml)")
    p.add_argument("--out-dir", type=Path, default=Path("draft"))
    p.add_argument("--refresh-players", action="store_true",
                   help="Force a re-fetch of /players/nfl even if the cache is fresh")
    p.add_argument("--cache-dir", default=None, help="Override the players cache directory")
    return p.parse_args()


def normalize_name(name: str) -> str:
    """Strip accents, punctuation, case and generational suffixes.

    'Amon-Ra St. Brown' -> 'amonrastbrown'; 'Chris Godwin Jr.' -> 'chrisgodwin'.
    Suffixes go because the sources disagree about carrying them.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    folded = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", folded)
    return re.sub(r"[^a-z0-9]", "", folded)


def load_rankings(path: Path) -> dict:
    if not path.exists():
        raise SleeperError(f"Rankings file {path} does not exist.")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SleeperError(f"Rankings file {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise SleeperError(f"Rankings file {path} must be a JSON object, got {type(raw).__name__}")

    players = raw.get("players")
    if not isinstance(players, list) or not players:
        raise SleeperError(f"Rankings file {path} has no non-empty 'players' list")

    for index, row in enumerate(players):
        if not isinstance(row, dict):
            raise SleeperError(
                f"Rankings file {path}: players[{index}] is {type(row).__name__}, expected object"
            )
        missing = [field for field in RANKING_FIELDS if row.get(field) in (None, "")]
        if missing:
            raise SleeperError(
                f"Rankings file {path}: players[{index}] ({row.get('name', '?')}) is missing "
                f"{', '.join(missing)}. Every ranking row needs {', '.join(RANKING_FIELDS)}."
            )
        if row["pos"] not in SKILL_POSITIONS:
            raise SleeperError(
                f"Rankings file {path}: {row['name']} has pos {row['pos']!r}. This league has no "
                f"kicker or defense slots, so the board only accepts {', '.join(SKILL_POSITIONS)}."
            )
    return raw


def index_notes(notes_dir: Path) -> dict[str, Path]:
    """player_id -> research note path, from the <stem>-<POS>-<player_id>.md convention."""
    if not notes_dir.exists():
        raise SleeperError(f"Research notes directory {notes_dir} does not exist.")
    notes: dict[str, Path] = {}
    for path in sorted(notes_dir.glob("*.md")):
        match = NOTE_FILENAME.match(path.name)
        if not match:
            raise SleeperError(
                f"Research note {path} does not match <stem>-<POS>-<player_id>.md. The player_id "
                "in the filename is the only join back to Sleeper, so it cannot be guessed."
            )
        pid = match.group("player_id")
        if pid in notes:
            raise SleeperError(f"Two research notes claim player_id {pid}: {notes[pid]} and {path}")
        notes[pid] = path
    if not notes:
        raise SleeperError(f"Research notes directory {notes_dir} contains no .md files")
    return notes


def load_scouting(path: Path, players: dict[str, dict]) -> dict[str, dict]:
    """player_id -> scouting entry, validated against the players dump.

    Already keyed by player_id, so no name join is needed -- but an id that is
    not in the dump means the note will never reach a board row, which is a
    silent loss of research. Every offender is named and nothing is written.
    """
    if not path.exists():
        raise SleeperError(
            f"Scouting notes {path} does not exist. It carries the per-player qualitative "
            "layer (one line each, plus risk/value/handcuff flags) that the ranking file has "
            "for only a handful of players. Pass --scouting to point elsewhere."
        )
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SleeperError(f"Scouting notes {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("notes"), dict):
        raise SleeperError(f"Scouting notes {path} must be an object with a 'notes' object")

    notes: dict[str, dict] = {}
    unknown: list[str] = []
    bad_flags: list[str] = []
    dangling: list[str] = []

    for pid, entry in raw["notes"].items():
        if not isinstance(entry, dict):
            raise SleeperError(f"Scouting notes {path}: entry for {pid} is not an object")
        if pid not in players:
            unknown.append(pid)
            continue
        for flag in entry.get("flags") or []:
            if flag not in SCOUTING_FLAGS:
                bad_flags.append(f"{pid}: {flag!r}")
        target = entry.get("handcuff_for")
        if target is not None and target not in players:
            dangling.append(f"{pid} -> {target}")
        notes[str(pid)] = entry

    problems = []
    if unknown:
        problems.append(
            f"{len(unknown)} scouting note(s) use a player_id absent from the players dump: "
            + ", ".join(unknown)
        )
    if bad_flags:
        problems.append(
            f"{len(bad_flags)} unknown flag(s) -- allowed: {', '.join(SCOUTING_FLAGS)}:\n  "
            + "\n  ".join(bad_flags)
        )
    if dangling:
        problems.append(
            f"{len(dangling)} handcuff_for link(s) point at an unknown player_id:\n  "
            + "\n  ".join(dangling)
        )
    if problems:
        raise SleeperError(f"{path}:\n" + "\n\n".join(problems) + "\n\nNothing was written.")
    return notes


def index_players(players: dict[str, dict]) -> dict[tuple[str, str], list[tuple[str, dict]]]:
    """(normalised name, fantasy position) -> candidate players.

    Keyed on fantasy_positions rather than `position` because Sleeper files some
    fantasy-relevant players under their defensive position -- Travis Hunter is
    position DB, fantasy_positions ['DB', 'WR'].
    """
    index: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    for pid, player in players.items():
        if not isinstance(player, dict):
            continue
        name = player.get("full_name")
        if not isinstance(name, str) or not name.strip():
            continue
        fantasy_positions = player.get("fantasy_positions")
        if not isinstance(fantasy_positions, list):
            continue
        for pos in SKILL_POSITIONS:
            if pos in fantasy_positions:
                index.setdefault((normalize_name(name), pos), []).append((str(pid), player))
    return index


def resolve(row: dict, candidates: list[tuple[str, dict]]) -> tuple[str, dict] | None:
    """Pick one player from same-name candidates, or None if still ambiguous.

    Prefers an exact `position` match, then an active player, then the lowest
    search_rank -- the most prominent player of a shared name is the one a
    ranking list this shallow means.
    """
    if len(candidates) == 1:
        return candidates[0]
    exact = [c for c in candidates if c[1].get("position") == row["pos"]]
    if len(exact) == 1:
        return exact[0]
    pool = exact or candidates
    active = [c for c in pool if c[1].get("active") is True]
    if len(active) == 1:
        return active[0]
    pool = active or pool
    ranked = [c for c in pool if isinstance(c[1].get("search_rank"), int)]
    if len(ranked) > 1:
        ranked.sort(key=lambda c: c[1]["search_rank"])
        if ranked[0][1]["search_rank"] != ranked[1][1]["search_rank"]:
            return ranked[0]
    elif len(ranked) == 1:
        return ranked[0]
    return None


def join(rankings: dict, players: dict[str, dict], notes: dict[str, Path],
         scouting: dict[str, dict]) -> list[dict]:
    """Ranking rows + player_id + research note path + scouting. Fails loud on any miss."""
    index = index_players(players)
    risk_flags = rankings.get("risk_flags") or {}
    if not isinstance(risk_flags, dict):
        raise SleeperError(f"Rankings 'risk_flags' must be an object, got {type(risk_flags).__name__}")
    flags_by_name = {normalize_name(name): text for name, text in risk_flags.items()}

    rows: list[dict] = []
    seen: dict[str, str] = {}
    unmatched: list[str] = []
    ambiguous: list[str] = []

    for row in rankings["players"]:
        key = normalize_name(row["name"])
        key = NAME_ALIASES.get(key, key)
        candidates = index.get((key, row["pos"]))
        if not candidates:
            unmatched.append(f"#{row['rank']} {row['name']} ({row['pos']}, {row['team']})")
            continue
        resolved = resolve(row, candidates)
        if resolved is None:
            ids = ", ".join(pid for pid, _ in candidates)
            ambiguous.append(f"#{row['rank']} {row['name']} ({row['pos']}) -> player_ids {ids}")
            continue
        pid, player = resolved
        if pid in seen:
            ambiguous.append(f"#{row['rank']} {row['name']} and {seen[pid]} both resolved to player_id {pid}")
            continue
        seen[pid] = row["name"]

        sleeper_team = player.get("team")
        note_path = notes.get(pid)
        scout = scouting.get(pid) or {}
        handcuff_for = scout.get("handcuff_for")
        rows.append({
            "player_id": pid,
            "rank": row["rank"],
            "name": row["name"],
            "sleeper_name": player.get("full_name"),
            "pos": row["pos"],
            "pos_rank": row["pos_rank"],
            "tier": row["tier"],
            "tier_pos": row.get("tier_pos"),
            "team": row["team"],
            "sleeper_team": sleeper_team,
            "team_disagreement": bool(sleeper_team) and sleeper_team != row["team"],
            "bye": row["bye"],
            "composite_score": row.get("composite_score"),
            "source_ranks": row.get("source_ranks") or {},
            "value_vs_market": row.get("value_vs_market"),
            "note": row.get("note"),
            "risk_flag": flags_by_name.get(normalize_name(row["name"])),
            "sleeper_status": player.get("status"),
            "sleeper_injury_status": player.get("injury_status"),
            "scouting": scout.get("text"),
            "flags": scout.get("flags") or [],
            "tier_label": scout.get("tier_label"),
            "handcuff_for": handcuff_for,
            "handcuff_for_name": (players[handcuff_for].get("full_name") if handcuff_for else None),
            "research_note": str(note_path) if note_path else None,
        })

    problems = []
    if unmatched:
        problems.append(
            f"{len(unmatched)} ranking row(s) matched no player in the Sleeper dump:\n  "
            + "\n  ".join(unmatched)
            + "\nAdd a NAME_ALIASES entry (ranking spelling -> Sleeper spelling, normalised) "
              "or refresh the players cache."
        )
    if ambiguous:
        problems.append(
            f"{len(ambiguous)} ranking row(s) could not be resolved to a single player:\n  "
            + "\n  ".join(ambiguous)
        )
    if problems:
        raise SleeperError("\n\n".join(problems) + "\n\nNothing was written.")

    rows.sort(key=lambda r: r["rank"])
    return rows


def notes_only(rows: list[dict], notes: dict[str, Path], players: dict[str, dict]) -> list[dict]:
    """Researched players who did not make the ranked list -- the late-round bin."""
    ranked_ids = {row["player_id"] for row in rows}
    extras = []
    for pid, path in notes.items():
        if pid in ranked_ids:
            continue
        player = players.get(pid)
        if not isinstance(player, dict):
            raise SleeperError(
                f"Research note {path} has player_id {pid}, which is not in the Sleeper players "
                "dump. Fix the filename or refresh the cache."
            )
        extras.append({
            "player_id": pid,
            "name": player.get("full_name") or pid,
            "pos": player.get("position"),
            "team": player.get("team"),
            "search_rank": player.get("search_rank"),
            "research_note": str(path),
        })
    extras.sort(key=lambda e: (e["search_rank"] is None, e["search_rank"] or 0, e["name"]))
    return extras


def pick_numbers(teams: int, rounds: int, reversal_round: int | None) -> dict[str, list[int]]:
    """Overall pick numbers per draft slot for a snake draft.

    A snake alternates direction every round. A reversal round repeats the
    PREVIOUS round's direction once, then alternation resumes from it -- so with
    reversal_round=3 rounds 2 and 3 both run last-slot-first, and round 4 runs
    forward again.
    """
    if teams < 1 or rounds < 1:
        raise SleeperError(f"Cannot build a pick order for teams={teams}, rounds={rounds}")
    if reversal_round is not None and not 2 <= reversal_round <= rounds:
        raise SleeperError(
            f"reversal_round={reversal_round} is outside rounds 2-{rounds}; Sleeper numbers "
            "reversal rounds from the round that repeats its predecessor's direction."
        )

    picks: dict[str, list[int]] = {str(slot): [] for slot in range(1, teams + 1)}
    reversed_direction = False
    for rnd in range(1, rounds + 1):
        if rnd > 1 and rnd != reversal_round:
            reversed_direction = not reversed_direction
        base = (rnd - 1) * teams
        for slot in range(1, teams + 1):
            offset = (teams - slot + 1) if reversed_direction else slot
            picks[str(slot)].append(base + offset)
    return picks


def verify_pick_numbers(picks: dict[str, list[int]], reference: dict | None, source: Path) -> None:
    """Cross-check the generated table against the research pack's own map."""
    if not reference:
        return
    for slot, expected in reference.items():
        got = picks.get(str(slot))
        if got is None:
            raise SleeperError(f"{source} lists draft slot {slot}, which the league config does not have.")
        if list(expected) != got:
            raise SleeperError(
                f"Pick-order disagreement for draft slot {slot}.\n"
                f"  generated: {got}\n  {source}: {list(expected)}\n"
                "Third-round reversal is undocumented by Sleeper; resolve this before drafting."
            )
    missing = sorted(set(picks) - set(map(str, reference)), key=int)
    if missing:
        raise SleeperError(f"{source} has no pick numbers for draft slot(s) {', '.join(missing)}.")


def load_league(path: Path) -> dict:
    """The handful of config.yaml fields the board and pick order depend on."""
    if not path.exists():
        raise SleeperError(f"League config {path} does not exist. Run sleeper-discover first.")
    import yaml

    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise SleeperError(f"League config {path} must be a mapping, got {type(raw).__name__}")
    league = {}
    for field in ("league_name", "league_id", "draft_id", "season", "teams", "rounds",
                  "reversal_round", "draft_type", "roster_positions", "scoring_settings"):
        league[field] = raw.get(field)
    for field in ("teams", "rounds"):
        if not isinstance(league[field], int) or league[field] < 1:
            raise SleeperError(f"League config {path}: {field} is {league[field]!r}, expected a positive int")
    return league


def has_scouting(row: dict) -> bool:
    return bool(row["scouting"] or row["flags"] or row["tier_label"])


def render_board_md(rows: list[dict], extras: list[dict], league: dict, rankings: dict) -> str:
    meta = rankings.get("meta") or {}
    positions = [p for p in (league.get("roster_positions") or []) if p != "BN"]
    out: list[str] = []
    out.append(f"# Draft board — {league.get('league_name') or 'league'} ({league.get('season')})")
    out.append("")
    out.append(
        f"{league['teams']} teams · {league['rounds']} rounds · {league.get('draft_type')}"
        + (f" w/ round-{league['reversal_round']} reversal" if league.get("reversal_round") else "")
        + f" · starters {'/'.join(positions)} · **no K, no DST**"
    )
    out.append("")
    out.append(f"{len(rows)} ranked players. Source: {meta.get('title', 'rankings')} "
               f"(generated {meta.get('generated', 'unknown')}). Scoring: {meta.get('scoring', 'unknown')}.")
    out.append("")
    out.append("Regenerate with `uv run sleeper-board`. **This file is the one to read** — "
               "`draft/board.json` holds the same board plus join fields, and exists as the input "
               "`sleeper-live` and other tooling parse. It is ~4.6x this file.")
    out.append("")
    out.append("**Columns** — `#` overall rank · `Pos` positional rank · `Bye` bye week · "
               "`id` Sleeper player_id (the join key to live picks) · `FFC`/`UD`/`RW` source ranks "
               "(FantasyFootballCalculator ADP / Underdog ADP / Rotoworld) · `Δ` this board minus the "
               "market, positive means we like them more than ADP does.")
    out.append("")
    out.append("**Flags** — `risk` injury or situation risk · `riser` trending up · `faller` "
               "trending down · `value` under-drafted relative to projection · `handcuff` "
               "contingent value behind a starter · `dead_zone` sits in the 2026 RB dead zone. "
               "Strategy behind all of it: `draft/STRATEGY.md`.")
    out.append("")
    out.append("Full research on a player: `research/players/` — the filename ends in their `id`.")
    out.append("")

    header = ("| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |\n"
              "|---:|---|---|---|---:|---|---:|---:|---:|---:|---|")

    def cell(value: object) -> str:
        return "-" if value is None else str(value)

    for tier in sorted({row["tier"] for row in rows}):
        tier_rows = [row for row in rows if row["tier"] == tier]
        first, last = tier_rows[0]["rank"], tier_rows[-1]["rank"]
        span = f"{first}-{last}" if first != last else str(first)
        out.append(f"## Tier {tier} — ranks {span} ({len(tier_rows)} players)")
        out.append("")
        out.append(header)
        for row in tier_rows:
            src = row["source_ranks"]
            annotations = []
            if row["risk_flag"]:
                annotations.append(f"**⚠ {row['risk_flag']}**")
            if row["sleeper_injury_status"]:
                tag = f"Sleeper: {row['sleeper_injury_status']}"
                annotations.append(
                    f"**⚠ {tag}**" if row["sleeper_injury_status"] in SEVERE_INJURY_STATUS else tag
                )
            if row["team_disagreement"]:
                annotations.append(f"**⚠ Sleeper has {row['sleeper_team']}**")
            if row["flags"]:
                annotations.append(" ".join(f"`{flag}`" for flag in row["flags"]))
            if row["handcuff_for_name"]:
                annotations.append(f"✂️ handcuff for {row['handcuff_for_name']}")
            if row["tier_label"]:
                annotations.append(f"_{row['tier_label']}_")
            if row["scouting"]:
                annotations.append(row["scouting"])
            if row["note"]:
                annotations.append(row["note"])
            if not row["research_note"]:
                annotations.append("_no research note_")
            out.append(
                f"| {row['rank']} | {row['pos_rank']} | {row['name']} | {row['team']} | {row['bye']} | "
                f"{row['player_id']} | {cell(src.get('ffc_halfppr_12team_adp'))} | "
                f"{cell(src.get('underdog_adp'))} | {cell(src.get('rotoworld_rank'))} | "
                f"{cell(row['value_vs_market'])} | {' · '.join(annotations)} |"
            )
        out.append("")

    out.append("## Positional index")
    out.append("")
    out.append("Positional rank → overall rank, for reading the runs and the cliffs.")
    out.append("")
    for pos in SKILL_POSITIONS:
        pos_rows = [row for row in rows if row["pos"] == pos]
        if not pos_rows:
            continue
        out.append(f"**{pos}** — " + " · ".join(
            f"{row['pos_rank']} {row['name']} (#{row['rank']}, T{row['tier']}, bye {row['bye']})"
            for row in pos_rows
        ))
        out.append("")

    out.append("## Researched but unranked")
    out.append("")
    out.append(f"{len(extras)} players with a research note that fell outside the ranked "
               f"{len(rows)}. Late-round and waiver material only.")
    out.append("")
    out.append("| Player | Pos | Tm | id | search_rank |")
    out.append("|---|---|---|---|---:|")
    for extra in extras:
        out.append(f"| {extra['name']} | {cell(extra['pos'])} | {cell(extra['team'])} | "
                   f"{extra['player_id']} | {cell(extra['search_rank'])} |")
    out.append("")

    out.append("## Provenance")
    out.append("")
    if meta.get("player_pool"):
        out.append(f"**Player pool** — {meta['player_pool']}")
        out.append("")
    if meta.get("method"):
        out.append(f"**Method** — {meta['method']}")
        out.append("")
    sources = meta.get("sources") or []
    if sources:
        out.append("**Sources**")
        out.append("")
        out.append("| Source | Date | Weight | Why |")
        out.append("|---|---|---|---|")
        for src in sources:
            out.append(f"| {cell(src.get('name'))} | {cell(src.get('date'))} | "
                       f"{cell(src.get('weight'))} | {cell(src.get('why'))} |")
        out.append("")
    mechanics = (rankings.get("draft_mechanics") or {}).get("explanation")
    if mechanics:
        out.append(f"**Draft mechanics** — {mechanics}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    args = parse_args()
    rankings = load_rankings(args.rankings)
    league = load_league(args.config)
    notes = index_notes(args.notes_dir)

    client = SleeperClient(**({"cache_dir": args.cache_dir} if args.cache_dir else {}))
    age = client.players_cache_age_hours()
    if age is None:
        print("players cache empty -- fetching /players/nfl (~5MB, once per day)", file=sys.stderr)
    else:
        print(f"players cache is {age:.1f}h old", file=sys.stderr)
    players = client.get_players(force_refresh=args.refresh_players)

    scouting = load_scouting(args.scouting, players)
    rows = join(rankings, players, notes, scouting)
    extras = notes_only(rows, notes, players)

    picks = pick_numbers(league["teams"], league["rounds"], league.get("reversal_round"))
    reference = (rankings.get("draft_mechanics") or {}).get("pick_numbers_by_draft_slot")
    verify_pick_numbers(picks, reference, args.rankings)

    generated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    board_path = args.out_dir / "board.json"
    board_path.write_text(json.dumps({
        "generated_at": generated_at,
        "join_key": "player_id",
        "source": {
            "rankings": str(args.rankings),
            "scouting_notes": str(args.scouting),
            "title": (rankings.get("meta") or {}).get("title"),
            "generated": (rankings.get("meta") or {}).get("generated"),
            "scoring": (rankings.get("meta") or {}).get("scoring"),
            "player_pool": (rankings.get("meta") or {}).get("player_pool"),
            "method": (rankings.get("meta") or {}).get("method"),
            "sources": (rankings.get("meta") or {}).get("sources"),
            "draft_mechanics": (rankings.get("draft_mechanics") or {}).get("explanation"),
        },
        "league": league,
        "counts": {
            "ranked": len(rows),
            "ranked_with_research_note": sum(1 for row in rows if row["research_note"]),
            "researched_unranked": len(extras),
            "with_scouting_note": sum(1 for row in rows if has_scouting(row)),
        },
        "plan": rankings.get("draft_day_plan"),
        "structural_notes": rankings.get("structural_notes"),
        "players": rows,
        "researched_unranked": extras,
    }, indent=1) + "\n")

    order_path = args.out_dir / "pick_order.json"
    order_path.write_text(json.dumps({
        "generated_at": generated_at,
        "teams": league["teams"],
        "rounds": league["rounds"],
        "reversal_round": league.get("reversal_round"),
        "verified_against": str(args.rankings) if reference else None,
        "picks_by_slot": picks,
        "slot_by_pick": {str(pick): int(slot) for slot, slot_picks in picks.items() for pick in slot_picks},
    }, indent=1) + "\n")

    md_path = args.out_dir / "board.md"
    md_path.write_text(render_board_md(rows, extras, league, rankings))

    without_notes = [f"#{row['rank']} {row['name']}" for row in rows if not row["research_note"]]
    print(f"\nwrote {board_path}, {md_path}, {order_path}", file=sys.stderr)
    print(f"{len(rows)} ranked players joined to player_ids; "
          f"{len(rows) - len(without_notes)} have a research note", file=sys.stderr)
    merged = sum(1 for row in rows if has_scouting(row))
    orphaned = sorted(set(scouting) - {row["player_id"] for row in rows})
    print(f"{merged} scouting notes merged from {args.scouting}", file=sys.stderr)
    if orphaned:
        print(f"{len(orphaned)} scouting note(s) for unranked players (not shown on the board): "
              + ", ".join(orphaned), file=sys.stderr)
    if without_notes:
        print(f"no research note for {len(without_notes)}: {', '.join(without_notes)}", file=sys.stderr)
    print(f"{len(extras)} researched players outside the ranked list", file=sys.stderr)
    if reference:
        print(f"pick order agrees with {args.rankings}", file=sys.stderr)
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

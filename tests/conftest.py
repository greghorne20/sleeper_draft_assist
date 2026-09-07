"""Offline fixtures. No test touches the network."""

from __future__ import annotations

import json
import random
import time

import pytest

from sleeper_draft.client import SleeperClient, SleeperError

TEAMS = [
    "ARI",
    "ATL",
    "BAL",
    "BUF",
    "CAR",
    "CHI",
    "CIN",
    "CLE",
    "DAL",
    "DEN",
    "DET",
    "GB",
    "HOU",
    "IND",
    "JAX",
    "KC",
    "LAC",
    "LAR",
    "LV",
    "MIA",
    "MIN",
    "NE",
    "NO",
    "NYG",
    "NYJ",
    "PHI",
    "PIT",
    "SEA",
    "SF",
    "TB",
    "TEN",
    "WAS",
]


def build_players(count: int = 600) -> dict[str, dict]:
    """A players map shaped like the real /players/nfl dump, including the
    awkward rows: null fantasy_positions, the 9999999 search_rank sentinel,
    free agents with team=null, and defenses with no full_name."""
    rng = random.Random(7)
    players: dict[str, dict] = {}

    for i in range(count):
        pos = rng.choice(["QB", "RB", "WR", "TE"])
        pid = str(1000 + i)
        players[pid] = {
            "player_id": pid,
            "full_name": f"First{i} O'Last{i}",
            "first_name": f"First{i}",
            "last_name": f"O'Last{i}",
            "position": pos,
            "fantasy_positions": [pos],
            "team": rng.choice(TEAMS),
            "active": True,
            "search_rank": i + 1,
        }

    for i, team in enumerate(TEAMS):
        players[f"K{i}"] = {
            "player_id": f"K{i}",
            "full_name": f"Kicker {team}",
            "position": "K",
            "fantasy_positions": ["K"],
            "team": team,
            "active": True,
            "search_rank": 2000 + i,
        }
        # Defenses: player_id is the team abbreviation, full_name is absent, and
        # -- as in the real dump -- search_rank is null for every defense.
        players[team] = {
            "player_id": team,
            "full_name": None,
            "first_name": team,
            "last_name": "Defense",
            "position": "DEF",
            "fantasy_positions": ["DEF"],
            "team": team,
            "active": True,
            "search_rank": None,
        }

    players["9001"] = {
        "player_id": "9001",
        "full_name": "Duplicate Player",
        "position": None,
        "fantasy_positions": None,
        "team": None,
        "active": False,
        "search_rank": None,
    }
    players["9002"] = {
        "player_id": "9002",
        "full_name": "Sentinel Guy",
        "position": "WR",
        "fantasy_positions": ["WR"],
        "team": "KC",
        "active": True,
        "search_rank": 9999999,
    }
    players["9003"] = {
        "player_id": "9003",
        "full_name": "Free Agent",
        "position": "RB",
        "fantasy_positions": ["RB"],
        "team": None,
        "active": True,
        "search_rank": 50,
    }
    return players


@pytest.fixture
def players_cache(tmp_path):
    """A fresh on-disk players cache the client will read without any HTTP."""
    cache = tmp_path / "cache"
    cache.mkdir()
    players = build_players()
    (cache / "players_nfl.json").write_text(json.dumps(players))
    (cache / "players_nfl.meta.json").write_text(
        json.dumps({"fetched_at": time.time(), "sport": "nfl", "count": len(players)})
    )
    return cache


@pytest.fixture
def byes_file(tmp_path):
    path = tmp_path / "byes.json"
    path.write_text(json.dumps({team: 5 + (i % 9) for i, team in enumerate(TEAMS)}))
    return path


LEAGUES = {
    "L2026": {
        "league_id": "L2026",
        "name": "The League",
        "season": "2026",
        "status": "pre_draft",
        "total_rosters": 12,
        "previous_league_id": "L2025",
        "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"],
        "scoring_settings": {"pass_td": 4.0, "rec": 0.5},
    },
    "L2025": {
        "league_id": "L2025",
        "name": "The League",
        "season": "2025",
        "status": "complete",
        "total_rosters": 12,
        "previous_league_id": "L2024",
        "roster_positions": ["QB"],
        "scoring_settings": {"rec": 0.5},
    },
    "L2024": {
        "league_id": "L2024",
        "name": "The League",
        "season": "2024",
        "status": "complete",
        "total_rosters": 12,
        "previous_league_id": None,
        "roster_positions": ["QB"],
        "scoring_settings": {"rec": 0.5},
    },
}

DRAFTS = {
    "D2026": {
        "draft_id": "D2026",
        "type": "snake",
        "status": "pre_draft",
        "league_id": "L2026",
        "settings": {"teams": 12, "rounds": 14, "reversal_round": 3, "pick_timer": 90},
        "slot_to_roster_id": {str(i): i for i in range(1, 13)},
        "draft_order": {"U1": 1, "U2": 2},
    },
    "D2025": {
        "draft_id": "D2025",
        "type": "snake",
        "status": "complete",
        "league_id": "L2025",
        "settings": {"teams": 12, "rounds": 14, "reversal_round": 3},
        "slot_to_roster_id": {str(i): i for i in range(1, 13)},
        "draft_order": {"U1": 1},
    },
    "D2024": {
        "draft_id": "D2024",
        "type": "snake",
        "status": "complete",
        "league_id": "L2024",
        "settings": {"teams": 12, "rounds": 14},  # no reversal_round key at all
        "slot_to_roster_id": {"1": 1},
        "draft_order": {},
    },
}

PICKS = {
    "D2025": [
        {
            "pick_no": n,
            "round": (n - 1) // 12 + 1,
            "draft_slot": ((n - 1) % 12) + 1,
            "player_id": str(n),
            "roster_id": ((n - 1) % 12) + 1,
            "metadata": {"first_name": "P", "last_name": str(n), "position": "RB", "team": "KC"},
        }
        for n in range(1, 12 * 14 + 1)
    ],
    "D2024": [],
}


# --- prior-season keeper data, shaped like the real 2025 league -------------
# Roster 1 is the interesting one: it carries every edge case the rules turn on.
KEEPER_ROSTERS = [
    # drafted+held (1001), the 2025 keeper (1002), dropped-and-re-added (1003),
    # a waiver pickup held to the end (1900), and a drafted player who was
    # dropped for good (1004, absent from `players`).
    {"roster_id": 1, "owner_id": "U1", "players": ["1001", "1002", "1003", "1900"]},
    {"roster_id": 2, "owner_id": "U2", "players": ["1005", "MISSING"]},
    {"roster_id": 3, "owner_id": "U3", "players": []},
]

KEEPER_USERS = [
    {"user_id": "U1", "display_name": "Alpha", "metadata": {"team_name": "Alpha Squad"}},
    # U2 has never set a team name -- Sleeper leaves the key off entirely.
    {"user_id": "U2", "display_name": "Beta", "metadata": {"allow_pn": "on"}},
    # U3 deliberately absent, so the report has to fall back to the roster id.
]

KEEPER_PICKS = [
    {
        "pick_no": 1,
        "round": 1,
        "roster_id": 1,
        "player_id": "1002",
        "is_keeper": True,
        "metadata": {"first_name": "Kept", "last_name": "Last Year", "position": "RB", "team": "KC"},
    },
    {
        "pick_no": 2,
        "round": 2,
        "roster_id": 1,
        "player_id": "1001",
        "is_keeper": None,
        "metadata": {"first_name": "Held", "last_name": "Allyear", "position": "WR", "team": "BUF"},
    },
    {
        "pick_no": 3,
        "round": 3,
        "roster_id": 1,
        "player_id": "1003",
        "is_keeper": None,
        "metadata": {"first_name": "Dropped", "last_name": "Readded", "position": "RB", "team": "SF"},
    },
    {
        "pick_no": 4,
        "round": 4,
        "roster_id": 1,
        "player_id": "1004",
        "is_keeper": None,
        "metadata": {"first_name": "Gone", "last_name": "Forgood", "position": "TE", "team": "NYJ"},
    },
    # Roster 2 traded for 1005: roster 3 drafted him, so he is nobody's keeper.
    {
        "pick_no": 5,
        "round": 5,
        "roster_id": 3,
        "player_id": "1005",
        "is_keeper": None,
        "metadata": {"first_name": "Traded", "last_name": "Away", "position": "WR", "team": "MIA"},
    },
    # A player the /players/nfl dump does not know; name must come from metadata.
    {
        "pick_no": 6,
        "round": 6,
        "roster_id": 2,
        "player_id": "MISSING",
        "is_keeper": None,
        "metadata": {"first_name": "Off", "last_name": "Dump", "position": "QB", "team": "LAR"},
    },
]

KEEPER_TRANSACTIONS = [
    # 1003 dropped in week 3 and re-added in week 9 -- on the final roster, but
    # did not stay all year. This is the case the transaction check exists for.
    {
        "status": "complete",
        "leg": 3,
        "type": "free_agent",
        "adds": None,
        "drops": {"1003": 1},
        "roster_ids": [1],
    },
    {"status": "complete", "leg": 9, "type": "waiver", "adds": {"1003": 1}, "drops": None, "roster_ids": [1]},
    # 1004 dropped for good.
    {
        "status": "complete",
        "leg": 5,
        "type": "free_agent",
        "adds": None,
        "drops": {"1004": 1},
        "roster_ids": [1],
    },
    # 1900 picked up off waivers and held to the end.
    {"status": "complete", "leg": 2, "type": "waiver", "adds": {"1900": 1}, "drops": None, "roster_ids": [1]},
    # A trade: roster 3 sends 1005 to roster 2.
    {
        "status": "complete",
        "leg": 6,
        "type": "trade",
        "adds": {"1005": 2},
        "drops": {"1005": 3},
        "roster_ids": [2, 3],
    },
    # Failed claim that would have dropped the one clean keeper -- must be ignored.
    {"status": "failed", "leg": 4, "type": "waiver", "adds": None, "drops": {"1001": 1}, "roster_ids": [1]},
]


class StubClient(SleeperClient):
    """SleeperClient with the HTTP methods replaced by canned league data."""

    def get_user(self, username_or_id):
        return {"user_id": "U1", "username": username_or_id, "display_name": "Me"}

    def get_user_leagues(self, user_id, season, sport="nfl"):
        return [LEAGUES["L2026"]] if str(season) == "2026" else []

    def get_league(self, league_id):
        if league_id not in LEAGUES:
            raise SleeperError(f"/league/{league_id} returned a JSON null body")
        return LEAGUES[league_id]

    def get_league_drafts(self, league_id):
        return [d for d in DRAFTS.values() if d["league_id"] == league_id]

    def get_draft(self, draft_id):
        if draft_id not in DRAFTS:
            raise SleeperError(f"/draft/{draft_id} returned a JSON null body")
        return DRAFTS[draft_id]

    def get_draft_picks(self, draft_id):
        return PICKS.get(draft_id, [])

    def get_rosters(self, league_id):
        return KEEPER_ROSTERS

    def get_league_users(self, league_id):
        return KEEPER_USERS

    def get_transactions(self, league_id, week):
        return [t for t in KEEPER_TRANSACTIONS if t["leg"] == week]


@pytest.fixture
def stub_client(monkeypatch):
    """Point every CLI module at the stub instead of the real client."""
    from sleeper_draft import batches, discover, past_draft

    for module in (discover, past_draft, batches):
        monkeypatch.setattr(module, "SleeperClient", StubClient)
    return StubClient


def build_rankings(players: dict[str, dict], count: int = 40) -> dict:
    """A rankings document shaped like research/rankings_2026.json.

    Keyed by NAME, like the real one -- the point of the board is to join it back
    to player_id. Includes the awkward rows: a suffix the sources disagree about,
    and a player whose research note is missing.
    """
    pool = sorted(
        (
            (pid, p)
            for pid, p in players.items()
            if p.get("position") in ("QB", "RB", "WR", "TE") and p.get("full_name")
        ),
        key=lambda item: item[1]["search_rank"],
    )[:count]
    by_pos: dict[str, int] = {}
    ranked = []
    for rank, (_pid, player) in enumerate(pool, start=1):
        pos = player["position"]
        by_pos[pos] = by_pos.get(pos, 0) + 1
        ranked.append(
            {
                "rank": rank,
                "name": player["full_name"],
                "pos": pos,
                "team": player["team"],
                "bye": 5 + (rank % 9),
                "pos_rank": f"{pos}{by_pos[pos]}",
                "tier": (rank - 1) // 10 + 1,
                "tier_pos": (rank - 1) % 10 + 1,
                "composite_score": float(rank),
                "source_ranks": {
                    "ffc_halfppr_12team_adp": rank + 0.5,
                    "underdog_adp": rank + 1.0,
                    "rotoworld_rank": rank,
                },
                "value_vs_market": 0,
                "note": None,
            }
        )
    return {
        "meta": {"title": "Test rankings", "generated": "2026-09-05", "scoring": "0.5 PPR"},
        "risk_flags": {ranked[0]["name"]: "Test flag - do not draft"},
        "draft_day_plan": {"core_principle": "test"},
        "structural_notes": ["no kickers, no defenses"],
        "draft_mechanics": {"pick_numbers_by_draft_slot": {}},
        "players": ranked,
    }


@pytest.fixture
def rankings_file(tmp_path, players_cache):
    players = json.loads((players_cache / "players_nfl.json").read_text())
    path = tmp_path / "rankings.json"
    path.write_text(json.dumps(build_rankings(players)))
    return path


@pytest.fixture
def notes_dir(tmp_path, rankings_file):
    """Research notes for every ranked player but the last -- the board must
    tolerate a ranked player with no note, and must not invent one."""
    ranked = json.loads(rankings_file.read_text())["players"]
    players = json.loads((tmp_path / "cache" / "players_nfl.json").read_text())
    by_name = {p["full_name"]: pid for pid, p in players.items() if p.get("full_name")}
    directory = tmp_path / "notes"
    directory.mkdir()
    for row in ranked[:-1]:
        pid = by_name[row["name"]]
        (directory / f"stub-{row['pos']}-{pid}.md").write_text(f"## {row['name']}\n")
    return directory


@pytest.fixture
def scouting_file(tmp_path, rankings_file, players_cache):
    """Scouting notes for the top few ranked players, keyed by player_id.

    Deliberately mixed: a text-only entry, a flags-only entry, and a handcuff
    pair -- the three shapes the real file carries.
    """
    ranked = json.loads(rankings_file.read_text())["players"]
    players = json.loads((players_cache / "players_nfl.json").read_text())
    by_name = {p["full_name"]: pid for pid, p in players.items() if p.get("full_name")}
    starter, backup, plain = (by_name[row["name"]] for row in ranked[:3])
    path = tmp_path / "scouting.json"
    path.write_text(
        json.dumps(
            {
                "source": "test",
                "notes": {
                    starter: {"text": "workhorse", "flags": ["value"]},
                    backup: {
                        "text": "best standalone handcuff",
                        "flags": ["handcuff"],
                        "handcuff_for": starter,
                    },
                    plain: {"flags": ["faller"], "tier_label": "dead zone R5-7"},
                },
            }
        )
    )
    return path


@pytest.fixture
def league_config(tmp_path):
    import yaml as _yaml

    path = tmp_path / "config.yaml"
    path.write_text(
        _yaml.safe_dump(
            {
                "league_name": "Test League",
                "league_id": "L2026",
                "draft_id": "D2026",
                "season": "2026",
                "teams": 12,
                "rounds": 13,
                "reversal_round": 3,
                "draft_type": "snake",
                "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"] + ["BN"] * 6,
                "scoring_settings": {"rec": 0.5},
            }
        )
    )
    return path


@pytest.fixture
def draft_artifacts(tmp_path, players_cache, rankings_file, notes_dir, scouting_file, league_config):
    """Real board.json + pick_order.json, built by the real generator.

    The live poller consumes exactly these two files, so building them through
    sleeper-board keeps the two modules honest about the shape they share.
    """
    import sys

    from sleeper_draft import board

    out = tmp_path / "draft"
    sys.argv = [
        "sleeper-board",
        "--cache-dir",
        str(players_cache),
        "--rankings",
        str(rankings_file),
        "--notes-dir",
        str(notes_dir),
        "--config",
        str(league_config),
        "--scouting",
        str(scouting_file),
        "--out-dir",
        str(out),
    ]
    board.main()
    return out


def make_keeper_picks(order: dict, board: dict, rounds_by_slot: dict[int, int]) -> list[dict]:
    """Keepers as Sleeper feeds them: ordinary picks carrying `is_keeper`, at the
    pick number their round cost implies.

    That is the shape the pick maths has to survive -- they arrive before the
    draft opens, scattered across the board rather than filling 1..N, so a
    "picks made" count says nothing about which pick is next.
    """
    picks = []
    for index, (slot, rnd) in enumerate(sorted(rounds_by_slot.items())):
        pick_no = int(order["picks_by_slot"][str(slot)][rnd - 1])
        row = board["players"][index]
        picks.append(
            {
                "pick_no": pick_no,
                "round": rnd,
                "draft_slot": slot,
                "roster_id": slot,
                "player_id": row["player_id"],
                "is_keeper": True,
                "metadata": {
                    "first_name": row["name"].split()[0],
                    "last_name": " ".join(row["name"].split()[1:]),
                    "position": row["pos"],
                    "team": row["team"],
                },
            }
        )
    return sorted(picks, key=lambda p: p["pick_no"])


def make_picks(order: dict, board: dict, count: int) -> list[dict]:
    """`count` picks in draft order, taking the board from the top.

    Once the board runs out the picks keep coming with player_ids that are not
    on it -- the off-board case, which is normal in a real draft.
    """
    rows = board["players"]
    picks = []
    for pick_no in range(1, count + 1):
        slot = order["slot_by_pick"][str(pick_no)]
        if pick_no <= len(rows):
            row = rows[pick_no - 1]
            pid, meta = (
                row["player_id"],
                {
                    "first_name": row["name"].split()[0],
                    "last_name": " ".join(row["name"].split()[1:]),
                    "position": row["pos"],
                    "team": row["team"],
                },
            )
        else:
            pid = f"offboard-{pick_no}"
            meta = {"first_name": "Off", "last_name": f"Board{pick_no}", "position": "WR", "team": "KC"}
        picks.append(
            {
                "pick_no": pick_no,
                "round": (pick_no - 1) // order["teams"] + 1,
                "draft_slot": slot,
                "roster_id": slot,
                "player_id": pid,
                "metadata": meta,
            }
        )
    return picks

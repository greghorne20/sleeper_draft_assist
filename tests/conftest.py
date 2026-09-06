"""Offline fixtures. No test touches the network."""

from __future__ import annotations

import json
import random
import time

import pytest

from sleeper_draft.client import SleeperClient, SleeperError

TEAMS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
    "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
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
            "player_id": f"K{i}", "full_name": f"Kicker {team}", "position": "K",
            "fantasy_positions": ["K"], "team": team, "active": True, "search_rank": 2000 + i,
        }
        # Defenses: player_id is the team abbreviation, full_name is absent, and
        # -- as in the real dump -- search_rank is null for every defense.
        players[team] = {
            "player_id": team, "full_name": None, "first_name": team, "last_name": "Defense",
            "position": "DEF", "fantasy_positions": ["DEF"], "team": team, "active": True,
            "search_rank": None,
        }

    players["9001"] = {
        "player_id": "9001", "full_name": "Duplicate Player", "position": None,
        "fantasy_positions": None, "team": None, "active": False, "search_rank": None,
    }
    players["9002"] = {
        "player_id": "9002", "full_name": "Sentinel Guy", "position": "WR",
        "fantasy_positions": ["WR"], "team": "KC", "active": True, "search_rank": 9999999,
    }
    players["9003"] = {
        "player_id": "9003", "full_name": "Free Agent", "position": "RB",
        "fantasy_positions": ["RB"], "team": None, "active": True, "search_rank": 50,
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
        "league_id": "L2026", "name": "The League", "season": "2026", "status": "pre_draft",
        "total_rosters": 12, "previous_league_id": "L2025",
        "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"],
        "scoring_settings": {"pass_td": 4.0, "rec": 0.5},
    },
    "L2025": {
        "league_id": "L2025", "name": "The League", "season": "2025", "status": "complete",
        "total_rosters": 12, "previous_league_id": "L2024",
        "roster_positions": ["QB"], "scoring_settings": {"rec": 0.5},
    },
    "L2024": {
        "league_id": "L2024", "name": "The League", "season": "2024", "status": "complete",
        "total_rosters": 12, "previous_league_id": None,
        "roster_positions": ["QB"], "scoring_settings": {"rec": 0.5},
    },
}

DRAFTS = {
    "D2026": {
        "draft_id": "D2026", "type": "snake", "status": "pre_draft", "league_id": "L2026",
        "settings": {"teams": 12, "rounds": 14, "reversal_round": 3, "pick_timer": 90},
        "slot_to_roster_id": {str(i): i for i in range(1, 13)},
        "draft_order": {"U1": 1, "U2": 2},
    },
    "D2025": {
        "draft_id": "D2025", "type": "snake", "status": "complete", "league_id": "L2025",
        "settings": {"teams": 12, "rounds": 14, "reversal_round": 3},
        "slot_to_roster_id": {str(i): i for i in range(1, 13)},
        "draft_order": {"U1": 1},
    },
    "D2024": {
        "draft_id": "D2024", "type": "snake", "status": "complete", "league_id": "L2024",
        "settings": {"teams": 12, "rounds": 14},  # no reversal_round key at all
        "slot_to_roster_id": {"1": 1},
        "draft_order": {},
    },
}

PICKS = {
    "D2025": [
        {
            "pick_no": n, "round": (n - 1) // 12 + 1, "draft_slot": ((n - 1) % 12) + 1,
            "player_id": str(n), "roster_id": ((n - 1) % 12) + 1,
            "metadata": {"first_name": "P", "last_name": str(n), "position": "RB", "team": "KC"},
        }
        for n in range(1, 12 * 14 + 1)
    ],
    "D2024": [],
}


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
        ((pid, p) for pid, p in players.items()
         if p.get("position") in ("QB", "RB", "WR", "TE") and p.get("full_name")),
        key=lambda item: item[1]["search_rank"],
    )[:count]
    by_pos: dict[str, int] = {}
    ranked = []
    for rank, (_pid, player) in enumerate(pool, start=1):
        pos = player["position"]
        by_pos[pos] = by_pos.get(pos, 0) + 1
        ranked.append({
            "rank": rank,
            "name": player["full_name"],
            "pos": pos,
            "team": player["team"],
            "bye": 5 + (rank % 9),
            "pos_rank": f"{pos}{by_pos[pos]}",
            "tier": (rank - 1) // 10 + 1,
            "tier_pos": (rank - 1) % 10 + 1,
            "composite_score": float(rank),
            "source_ranks": {"ffc_halfppr_12team_adp": rank + 0.5, "underdog_adp": rank + 1.0,
                             "rotoworld_rank": rank},
            "value_vs_market": 0,
            "note": None,
        })
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
    path.write_text(json.dumps({
        "source": "test",
        "notes": {
            starter: {"text": "workhorse", "flags": ["value"]},
            backup: {"text": "best standalone handcuff", "flags": ["handcuff"],
                     "handcuff_for": starter},
            plain: {"flags": ["faller"], "tier_label": "dead zone R5-7"},
        },
    }))
    return path


@pytest.fixture
def league_config(tmp_path):
    import yaml as _yaml

    path = tmp_path / "config.yaml"
    path.write_text(_yaml.safe_dump({
        "league_name": "Test League", "league_id": "L2026", "draft_id": "D2026",
        "season": "2026", "teams": 12, "rounds": 13, "reversal_round": 3,
        "draft_type": "snake",
        "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"] + ["BN"] * 6,
        "scoring_settings": {"rec": 0.5},
    }))
    return path

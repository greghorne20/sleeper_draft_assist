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

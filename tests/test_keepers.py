from __future__ import annotations

import json
import sys

import pytest
from conftest import KEEPER_PICKS, KEEPER_ROSTERS, KEEPER_TRANSACTIONS, KEEPER_USERS

from sleeper_draft import keepers
from sleeper_draft.client import SleeperError

PLAYERS = {
    "1001": {"full_name": "Held Allyear", "position": "WR", "team": "BUF"},
    "1002": {"full_name": "Kept Last Year", "position": "RB", "team": "KC"},
    "1003": {"full_name": "Dropped Readded", "position": "RB", "team": "SF"},
    "1004": {"full_name": "Gone Forgood", "position": "TE", "team": "NYJ"},
    "1005": {"full_name": "Traded Away", "position": "WR", "team": "MIA"},
    "1900": {"full_name": "Waiver Pickup", "position": "WR", "team": "DEN"},
}


def rule(board=None):
    return keepers.eligible_keepers(
        KEEPER_PICKS, KEEPER_ROSTERS, KEEPER_USERS, KEEPER_TRANSACTIONS, PLAYERS, board
    )


def team(report, roster_id):
    return next(t for t in report["teams"] if t["roster_id"] == roster_id)


def eligible_ids(report, roster_id):
    return {p["player_id"] for p in team(report, roster_id)["eligible"]}


def test_drafted_and_held_all_year_is_eligible_at_its_draft_round():
    entry = next(p for p in team(rule(), 1)["eligible"] if p["player_id"] == "1001")
    assert entry["round_cost"] == 2
    assert entry["drafted_at_pick"] == 2
    assert entry["name"] == "Held Allyear"


def test_dropped_and_re_added_is_ineligible_despite_the_final_roster():
    """The whole reason this reads the transaction log instead of the roster."""
    report = rule()
    assert "1003" in {str(p) for p in KEEPER_ROSTERS[0]["players"]}, "fixture: on final roster"
    assert "1003" not in eligible_ids(report, 1)
    # And it is surfaced rather than silently dropped.
    flagged = {d["player_id"] for d in report["divergences"]}
    assert flagged == {"1003"}


def test_last_seasons_keeper_is_blocked_with_a_reason():
    blocked = team(rule(), 1)["blocked"]
    assert [p["player_id"] for p in blocked] == ["1002"]
    assert blocked[0]["reason"] == "kept last season"
    assert "1002" not in eligible_ids(rule(), 1)


def test_waiver_pickup_held_to_the_end_is_not_eligible():
    report = rule()
    assert "1900" not in eligible_ids(report, 1)
    assert team(report, 1)["excluded"]["held_but_undrafted"] == 1


def test_drafted_then_dropped_for_good_is_ineligible_and_counted():
    report = rule()
    assert "1004" not in eligible_ids(report, 1)
    assert team(report, 1)["excluded"]["drafted_but_left"] == 1
    # It left the roster, so it is not a "dropped and re-acquired" divergence.
    assert "1004" not in {d["player_id"] for d in report["divergences"]}


def test_a_traded_player_is_eligible_for_neither_team():
    report = rule()
    assert "1005" not in eligible_ids(report, 2)  # acquired mid-season, did not draft him
    assert "1005" not in eligible_ids(report, 3)  # drafted him but shipped him out


def test_failed_transactions_are_ignored():
    """A failed waiver claim never moved anyone, so it cannot cost eligibility."""
    assert any(t["status"] == "failed" and "1001" in (t["drops"] or {}) for t in KEEPER_TRANSACTIONS), (
        "fixture: a failed drop of 1001"
    )
    assert "1001" in eligible_ids(rule(), 1)


def test_name_falls_back_to_pick_metadata_when_the_dump_lacks_the_player():
    entry = next(p for p in team(rule(), 2)["eligible"] if p["player_id"] == "MISSING")
    assert entry["name"] == "Off Dump"
    assert entry["pos"] == "QB"


def test_team_with_no_eligible_players_renders_explicitly():
    report = rule()
    assert team(report, 3)["eligible"] == []
    md = keepers.render_keepers_md(
        report, {"for_league_name": "L", "for_season": "2026", "target_season": "2025"}
    )
    assert "_No eligible keepers._" in md


def test_team_name_is_used_when_the_manager_has_set_one():
    entry = team(rule(), 1)
    assert entry["team_name"] == "Alpha Squad"
    assert entry["display_name"] == "Alpha"  # the manager is still recorded
    md = keepers.render_keepers_md(
        rule(), {"for_league_name": "L", "for_season": "2026", "target_season": "2025"}
    )
    assert "## Alpha Squad" in md
    assert "## Alpha\n" not in md


def test_team_name_falls_back_to_the_manager_then_the_roster_id():
    assert team(rule(), 2)["team_name"] == "Beta"  # metadata has no team_name
    assert team(rule(), 3)["team_name"] == "roster 3"  # no user record at all
    assert team(rule(), 3)["display_name"] is None


def test_blank_team_name_is_treated_as_unset():
    users = [{"user_id": "U1", "display_name": "Alpha", "metadata": {"team_name": "   "}}]
    report = keepers.eligible_keepers(KEEPER_PICKS, KEEPER_ROSTERS, users, KEEPER_TRANSACTIONS, PLAYERS)
    assert team(report, 1)["team_name"] == "Alpha"


def test_eligible_players_are_ordered_by_round_cost():
    for entry in rule()["teams"]:
        costs = [p["round_cost"] for p in entry["eligible"]]
        assert costs == sorted(costs)


BOARD = {
    "1001": {
        "player_id": "1001",
        "rank": 12,
        "pos_rank": "WR5",
        "tier": 2,
        "scouting": "our private read",
        "flags": ["value"],
        "source_ranks": {"ffc_halfppr_12team_adp": 18.4, "ffc_rank": 18},
    }
}


def test_public_adp_is_attached_when_a_board_is_supplied():
    entry = next(p for p in team(rule(BOARD), 1)["eligible"] if p["player_id"] == "1001")
    assert entry["adp"] == 18.4
    md = keepers.render_keepers_md(
        rule(BOARD), {"for_league_name": "L", "for_season": "2026", "target_season": "2025"}
    )
    assert "2026 ADP" in md
    assert "18.4" in md


def test_our_own_rank_tier_and_scouting_never_reach_the_report():
    """keepers.md gets circulated to the league; the aggregate board does not."""
    report = rule(BOARD)
    entry = next(p for p in team(report, 1)["eligible"] if p["player_id"] == "1001")
    for private in (
        "rank",
        "pos_rank",
        "tier",
        "scouting",
        "flags",
        "board_rank",
        "board_tier",
        "board_pos_rank",
    ):
        assert private not in entry, private

    blob = json.dumps(report) + keepers.render_keepers_md(
        report, {"for_league_name": "L", "for_season": "2026", "target_season": "2025"}
    )
    assert "our private read" not in blob
    assert "WR5" not in blob


def test_a_board_row_without_adp_adds_nothing():
    entry = next(
        p
        for p in team(rule({"1001": {"player_id": "1001", "rank": 12}}), 1)["eligible"]
        if p["player_id"] == "1001"
    )
    assert "adp" not in entry


def test_board_is_optional():
    entry = next(p for p in team(rule(), 1)["eligible"] if p["player_id"] == "1001")
    assert "adp" not in entry


def test_missing_board_file_is_not_an_error(tmp_path):
    assert keepers.load_board(tmp_path / "absent.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    assert keepers.load_board(bad) == {}


def test_no_rosters_is_a_hard_error():
    with pytest.raises(SleeperError, match="no rosters"):
        keepers.eligible_keepers(KEEPER_PICKS, [], KEEPER_USERS, [], PLAYERS)


def test_no_picks_is_a_hard_error():
    with pytest.raises(SleeperError, match="no picks"):
        keepers.eligible_keepers([], KEEPER_ROSTERS, KEEPER_USERS, [], PLAYERS)


def test_pick_without_a_roster_id_errors_rather_than_being_dropped():
    picks = KEEPER_PICKS + [{"pick_no": 7, "round": 7, "roster_id": None, "player_id": "1001"}]
    with pytest.raises(SleeperError, match="cannot be attributed to a team"):
        keepers.eligible_keepers(picks, KEEPER_ROSTERS, KEEPER_USERS, [], PLAYERS)


def test_totals_add_up():
    report = rule()
    assert report["totals"]["teams"] == 3
    assert report["totals"]["eligible"] == sum(len(t["eligible"]) for t in report["teams"])
    assert report["totals"]["blocked"] == 1


def test_end_to_end_writes_both_files(tmp_path, monkeypatch, players_cache):
    class Client:
        def __init__(self, **kwargs):
            pass

        def get_league(self, league_id):
            return {
                "league_id": league_id,
                "season": "2026" if league_id == "L2026" else "2025",
                "name": "Test League",
                "previous_league_id": "L2025",
            }

        def get_league_drafts(self, league_id):
            return [{"draft_id": "DK", "league_id": league_id, "created": 1}]

        def get_draft_picks(self, draft_id):
            return KEEPER_PICKS

        def get_rosters(self, league_id):
            return KEEPER_ROSTERS

        def get_league_users(self, league_id):
            return KEEPER_USERS

        def get_transactions(self, league_id, week):
            return [t for t in KEEPER_TRANSACTIONS if t["leg"] == week]

        def get_players(self, **kwargs):
            return PLAYERS

    monkeypatch.setattr(keepers, "SleeperClient", Client)
    monkeypatch.setattr(
        keepers,
        "walk_back",
        lambda c, lid, back, season: (
            c.get_league("L2025"),
            [
                {"league_id": "L2026", "season": "2026", "name": "Test League"},
                {"league_id": "L2025", "season": "2025", "name": "Test League"},
            ],
        ),
    )
    out = tmp_path / "draft"
    sys.argv = [
        "sleeper-keepers",
        "--league-id",
        "L2026",
        "--back",
        "1",
        "--cache-dir",
        str(players_cache),
        "--out-dir",
        str(out),
        "--board",
        str(tmp_path / "no-board.json"),
        "--weeks",
        "10",
    ]
    assert keepers.main() == 0

    report = json.loads((out / "keepers.json").read_text())
    assert report["source"]["target_season"] == "2025"
    assert report["source"]["for_season"] == "2026"
    md = (out / "keepers.md").read_text()
    assert "# Keeper eligibility" in md
    assert "## Alpha Squad" in md
    assert "Held Allyear" in md
    assert "Kept Last Year — kept last season" in md
    assert "## Dropped and re-acquired" in md

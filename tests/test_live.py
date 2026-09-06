from __future__ import annotations

import json
import sys

import pytest
from conftest import make_picks

from sleeper_draft import live
from sleeper_draft.client import SleeperError

DRAFT = {"draft_id": "D2026", "status": "drafting", "draft_order": {"U1": 7}}


def artifacts(draft_artifacts):
    board = json.loads((draft_artifacts / "board.json").read_text())
    order = json.loads((draft_artifacts / "pick_order.json").read_text())
    return board, order


def state_after(draft_artifacts, count, my_slot=12, cushion=4, limit=30, draft=None):
    board, order = artifacts(draft_artifacts)
    picks = make_picks(order, board, count)
    return live.summarize(board, order, draft or DRAFT, picks, my_slot, cushion, limit)


def test_pick_clock_tracks_the_3rr_order(draft_artifacts):
    state = state_after(draft_artifacts, 12, my_slot=12)
    # 12 picks in: pick 13 is next, and under 3RR slot 12 picks 12 AND 13.
    assert state["picks_made"] == 12
    assert state["current_pick"] == 13
    assert state["current_round"] == 2
    assert state["on_the_clock_slot"] == 12
    assert state["is_my_turn"] is True
    assert state["my_next_pick"] == 13
    assert state["my_pick_after_next"] == 25


def test_horizon_is_the_following_pick_when_on_the_clock(draft_artifacts):
    state = state_after(draft_artifacts, 12, my_slot=12)
    # On the clock at 13. I take 13 myself, so the picks I have to survive are
    # 14..24 -- eleven of them -- before 25 comes back to me.
    assert state["is_my_turn"] is True
    assert state["survive_until_pick"] == 25
    assert state["picks_before_horizon"] == 11


def test_horizon_is_my_next_pick_when_waiting(draft_artifacts):
    state = state_after(draft_artifacts, 5, my_slot=12)
    # Pick 6 is up and it is not mine, so picks 6..11 are all other teams --
    # six of them -- and then I pick at 12. current_pick counts here precisely
    # because I have not used it.
    assert state["is_my_turn"] is False
    assert state["my_next_pick"] == 12
    assert state["survive_until_pick"] == 12
    assert state["picks_before_horizon"] == 6


def test_the_count_is_the_picks_actually_made_by_other_teams(draft_artifacts):
    """Walk the whole first round and check the count against a literal tally."""
    board, order = artifacts(draft_artifacts)
    for made in range(0, 24):
        picks = make_picks(order, board, made)
        state = live.summarize(board, order, DRAFT, picks, 12, 4, 30)
        horizon, current = state["survive_until_pick"], state["current_pick"]
        if horizon is None or current is None:
            continue
        mine = set(state["my_picks"])
        # Every pick strictly before the horizon that is not one I make myself.
        expected = len([n for n in range(current, horizon) if n not in mine])
        assert state["picks_before_horizon"] == expected, (
            f"{made} made, on the clock={state['is_my_turn']}, "
            f"current={current}, horizon={horizon}"
        )


def test_one_pick_away_counts_exactly_one(draft_artifacts):
    board, order = artifacts(draft_artifacts)
    # Slot 12 picks at 12; with 10 made, pick 11 is up and only slot 11 is ahead.
    state = live.summarize(board, order, DRAFT, make_picks(order, board, 10), 12, 4, 30)
    assert state["current_pick"] == 11
    assert state["my_next_pick"] == 12
    assert state["picks_before_horizon"] == 1


def test_drafted_players_leave_the_available_board(draft_artifacts):
    board, _ = artifacts(draft_artifacts)
    state = state_after(draft_artifacts, 10)
    taken = {row["player_id"] for row in board["players"][:10]}
    available = {row["player_id"] for row in state["best_available"]}
    assert not (taken & available)
    assert state["available_count"] == len(board["players"]) - 10
    assert state["best_available"][0]["rank"] == 11


def test_my_roster_collects_only_my_slots_picks(draft_artifacts):
    state = state_after(draft_artifacts, 26, my_slot=12)
    # Slot 12 under 3RR owns picks 12, 13 and 25.
    assert [p["pick_no"] for p in state["my_roster"]] == [12, 13, 25]
    assert all(p["draft_slot"] == 12 for p in state["my_roster"])


def test_at_risk_is_bounded_by_the_horizon_plus_cushion(draft_artifacts):
    state = state_after(draft_artifacts, 5, my_slot=12, cushion=4)
    threshold = state["survive_until_pick"] + 4
    assert state["at_risk"], "expected some players inside the horizon"
    for row in state["at_risk"]:
        assert row["adp"] <= threshold
    # And nobody safely beyond it crept in.
    risky = {row["player_id"] for row in state["at_risk"]}
    for row in state["best_available"]:
        adp = row.get("adp")
        if adp is not None and adp > threshold:
            assert row["player_id"] not in risky


def test_cushion_widens_the_at_risk_list(draft_artifacts):
    narrow = state_after(draft_artifacts, 5, cushion=0)
    wide = state_after(draft_artifacts, 5, cushion=20)
    assert len(wide["at_risk"]) > len(narrow["at_risk"])


def test_tier_status_counts_only_undrafted_players(draft_artifacts):
    board, _ = artifacts(draft_artifacts)
    state = state_after(draft_artifacts, 10)
    counted = sum(n for tiers in state["tier_status"].values() for n in tiers.values())
    assert counted == len(board["players"]) - 10


def test_off_board_picks_are_recorded_not_fatal(draft_artifacts):
    board, _ = artifacts(draft_artifacts)
    over = len(board["players"]) + 3
    state = state_after(draft_artifacts, over)
    assert len(state["off_board_picks"]) == 3
    assert all(entry["on_board"] is False for entry in state["off_board_picks"])
    assert state["off_board_picks"][0]["name"].startswith("Off Board")
    # An off-board pick still consumes a pick number.
    assert state["picks_made"] == over


def test_roster_needs_fill_dedicated_slots_before_flex():
    positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"] + ["BN"] * 6
    roster = [{"pos": p} for p in ("RB", "RB", "WR")]
    needs = live.roster_needs(roster, positions)
    assert needs["starters_filled"] == {"QB": 0, "RB": 2, "WR": 1, "TE": 0}
    assert needs["flex_filled"] == 0
    assert set(needs["open_starters"]) == {"QB", "WR", "TE"}
    assert needs["flex_open"] is True


def test_roster_needs_spills_the_third_rb_into_flex():
    positions = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"] + ["BN"] * 6
    roster = [{"pos": p} for p in ("RB", "RB", "RB", "WR", "WR", "TE", "QB")]
    needs = live.roster_needs(roster, positions)
    assert needs["open_starters"] == []
    assert needs["flex_filled"] == 1
    assert needs["flex_open"] is False


def test_position_run_counts_the_recent_window(draft_artifacts):
    state = state_after(draft_artifacts, 20)
    assert len(state["recent_picks"]) == live.RUN_WINDOW
    assert sum(state["position_run"].values()) == live.RUN_WINDOW


def test_completed_draft_reports_no_current_pick(draft_artifacts):
    board, order = artifacts(draft_artifacts)
    state = state_after(draft_artifacts, order["teams"] * order["rounds"])
    assert state["current_pick"] is None
    assert state["picks_remaining"] == 0
    assert state["is_my_turn"] is False
    assert "Draft complete" in live.render_now_md(state)


def test_without_a_slot_the_timing_maths_is_skipped_not_guessed(draft_artifacts):
    state = state_after(draft_artifacts, 5, my_slot=None)
    assert state["my_slot"] is None
    assert state["my_next_pick"] is None
    assert state["survive_until_pick"] is None
    assert state["at_risk"] == []
    assert state["my_roster"] == []
    assert "My slot is not set" in live.render_now_md(state)


def test_now_md_carries_the_decision_surface(draft_artifacts):
    state = state_after(draft_artifacts, 5, my_slot=12)
    md = live.render_now_md(state)
    assert "## Pick 6 of 156" in md
    assert "On the clock: slot 6" in md
    assert "## My roster" in md
    assert "## Best available" in md
    assert "## Tiers remaining" in md
    assert f"At risk before pick {state['survive_until_pick']}" in md
    # Every listed player carries the join key back to the board.
    for row in state["best_available"]:
        assert f"| {row['player_id']} |" in md


def test_writes_both_files(tmp_path, draft_artifacts):
    state = state_after(draft_artifacts, 5)
    out = tmp_path / "state"
    md_path, json_path = live.write_state(state, out)
    assert md_path.exists() and json_path.exists()
    assert json.loads(json_path.read_text())["picks_made"] == 5
    assert md_path.read_text().startswith("# Draft state")


def test_resolve_slot_prefers_explicit_slot(draft_artifacts):
    _, order = artifacts(draft_artifacts)
    slot, why = live.resolve_slot(DRAFT, order, 4, "someone", client=None)
    assert slot == 4
    assert "--slot 4" in why


def test_resolve_slot_rejects_a_slot_outside_the_draft(draft_artifacts):
    _, order = artifacts(draft_artifacts)
    with pytest.raises(SleeperError, match="not one of the 12 slots"):
        live.resolve_slot(DRAFT, order, 13, None, client=None)


def test_resolve_slot_from_username(draft_artifacts):
    _, order = artifacts(draft_artifacts)

    class Client:
        def get_user(self, name):
            return {"user_id": "U1", "username": name}

    slot, why = live.resolve_slot(DRAFT, order, None, "me", Client())
    assert slot == 7
    assert "slot 7" in why


def test_username_not_in_draft_order_errors(draft_artifacts):
    _, order = artifacts(draft_artifacts)

    class Client:
        def get_user(self, name):
            return {"user_id": "STRANGER", "username": name}

    with pytest.raises(SleeperError, match="not in this draft's draft_order"):
        live.resolve_slot(DRAFT, order, None, "stranger", Client())


def test_missing_draft_order_errors_rather_than_guessing(draft_artifacts):
    _, order = artifacts(draft_artifacts)
    with pytest.raises(SleeperError, match="no draft_order yet"):
        live.resolve_slot({"draft_id": "D", "draft_order": {}}, order, None, "me", client=None)


def test_missing_board_errors_and_points_at_the_generator(tmp_path):
    with pytest.raises(SleeperError, match="sleeper-board"):
        live.load_board(tmp_path / "nope.json")


def test_end_to_end_writes_state_without_touching_the_network(
        tmp_path, monkeypatch, draft_artifacts, players_cache):
    board, order = artifacts(draft_artifacts)
    picks = make_picks(order, board, 12)

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_draft(self, draft_id):
            return DRAFT

        def get_draft_picks(self, draft_id):
            return picks

    monkeypatch.setattr(live, "SleeperClient", Client)
    out = tmp_path / "state"
    sys.argv = ["sleeper-live", "--board", str(draft_artifacts / "board.json"),
                "--pick-order", str(draft_artifacts / "pick_order.json"),
                "--draft-id", "D2026", "--slot", "12", "--out-dir", str(out)]
    assert live.main() == 0

    state = json.loads((out / "state.json").read_text())
    assert state["picks_made"] == 12
    assert state["is_my_turn"] is True
    assert (out / "NOW.md").read_text().count("| ") > 10


def test_display_row_keeps_the_display_fields_and_flattens_adp():
    row = {
        "player_id": "1", "rank": 5, "pos_rank": "RB3", "pos": "RB", "name": "A Back",
        "team": "KC", "bye": 6, "tier": 1, "value_vs_market": 2, "scouting": "workhorse",
        "flags": ["value"], "risk_flag": None, "note": None, "handcuff_for_name": None,
        "sleeper_injury_status": None,
        "source_ranks": {"ffc_halfppr_12team_adp": 4.5, "ffc_rank": 4},
        # None of these belong in a live view.
        "sleeper_name": "A Back", "sleeper_team": "KC", "team_disagreement": False,
        "tier_pos": 3, "composite_score": 5.0, "sleeper_status": "Active",
        "tier_label": "tier 1", "handcuff_for": None,
        "research_note": "research/players/back-a-RB-1.md",
    }
    out = live.display_row(row)
    assert out == {
        "player_id": "1", "rank": 5, "pos_rank": "RB3", "pos": "RB", "name": "A Back",
        "team": "KC", "bye": 6, "tier": 1, "value_vs_market": 2, "flags": ["value"],
        "scouting": "workhorse", "adp": 4.5,
    }
    # Empty values are dropped rather than carried as nulls.
    assert "risk_flag" not in out
    assert "note" not in out


def test_display_row_survives_a_player_with_no_adp():
    row = {"player_id": "2", "rank": 200, "pos_rank": "WR90", "pos": "WR", "name": "Deep Cut",
           "team": "NYJ", "bye": 9, "tier": 12, "source_ranks": {}}
    out = live.display_row(row)
    assert "adp" not in out
    assert out["name"] == "Deep Cut"
    # And the table still renders that row, with a dash for the missing ADP.
    assert "| - |" in "\n".join(live._player_table([out]))


def test_state_json_rows_carry_adp_and_drop_the_join_fields(tmp_path, draft_artifacts):
    state = state_after(draft_artifacts, 5, my_slot=12)
    _, json_path = live.write_state(state, tmp_path / "state")
    rows = json.loads(json_path.read_text())["best_available"]

    assert rows, "expected players on the board"
    for row in rows:
        assert set(row) <= set(live.DISPLAY_FIELDS) | {"adp"}
        for absent in ("source_ranks", "research_note", "sleeper_name", "composite_score",
                       "tier_pos", "team_disagreement", "sleeper_status"):
            assert absent not in row
    assert any("adp" in row for row in rows)


def test_projection_does_not_touch_roster_or_recent_picks(draft_artifacts):
    """Those entries are built in the pick loop, not projected from board rows."""
    state = state_after(draft_artifacts, 26, my_slot=12)
    for entry in state["my_roster"] + state["recent_picks"]:
        assert {"pick_no", "round", "draft_slot", "roster_id", "on_board"} <= set(entry)


def test_state_json_is_much_smaller_than_the_full_rows(tmp_path, draft_artifacts):
    """The point of the projection: a renderer polls this file, so keep it small."""
    board, _ = artifacts(draft_artifacts)
    state = state_after(draft_artifacts, 5, my_slot=12)
    _, json_path = live.write_state(state, tmp_path / "state")

    projected = len(json_path.read_text())
    untrimmed = dict(state)
    by_id = {row["player_id"]: row for row in board["players"]}
    for key in ("best_available", "at_risk"):
        untrimmed[key] = [by_id[row["player_id"]] for row in state[key]]
    assert projected < len(json.dumps(untrimmed, indent=1)) / 2

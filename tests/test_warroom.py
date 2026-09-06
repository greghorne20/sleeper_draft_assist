"""The war-room layer's pure half: validation, the refresh trigger, the prompt.

No model and no network. The parts that decide what is true are testable on
their own, exactly as `summarize()` and `eligible_keepers()` are -- the model is
only asked for the judgement.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from conftest import make_picks

from sleeper_draft import live
from sleeper_draft.warroom import agent as A
from sleeper_draft.warroom import brief as B
from sleeper_draft.warroom import runner as R
from sleeper_draft.warroom import tools as T

DRAFT = {"draft_id": "D2026", "status": "drafting", "draft_order": {"U1": 7}}
NAMES = {n: f"Team {chr(64 + n)}" for n in range(1, 13)}


def artifacts(draft_artifacts):
    board = json.loads((draft_artifacts / "board.json").read_text())
    order = json.loads((draft_artifacts / "pick_order.json").read_text())
    return board, order


def league(draft_artifacts, count):
    board, order = artifacts(draft_artifacts)
    picks = make_picks(order, board, count)
    return board, live.summarize_all(board, order, DRAFT, picks, 4, 30, NAMES, 12)


def candidate(row, why="Because the board says so."):
    return B.Candidate(player_id=row["player_id"], name=row["name"], pos=row["pos"], why=why)


def a_brief(available, first=0, second=1, **kw):
    rows = list(available.values())
    return B.Brief(strategy="Anchor RB, then best available.",
                   pick=candidate(rows[first]), alternative=candidate(rows[second]), **kw)


# --- what is still on the board ---------------------------------------------


def test_drafted_ids_covers_every_pick_not_just_mine(draft_artifacts):
    _, state = league(draft_artifacts, 26)
    taken = B.drafted_ids(state)
    assert len(taken) == 26
    # Every seat's picks are in there, not only slot 12's.
    for slot in ("1", "5", "12"):
        for entry in state["rosters_by_slot"][slot]:
            assert entry["player_id"] in taken


def test_available_index_is_the_whole_board_minus_the_drafted(draft_artifacts):
    board, state = league(draft_artifacts, 5)
    available = B.available_index(board, state)
    assert len(available) == len(board["players"]) - 5
    assert not (set(available) & B.drafted_ids(state))
    # Deeper than the thirty the prompt shows -- a late handcuff is a legal pick.
    assert len(available) > len(state["best_available"])


# --- validation: the gate that stops a drafted player being recommended ------


def test_a_clean_brief_passes(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    assert B.validate_brief(a_brief(available), available) == []


def test_a_drafted_player_is_refused(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    gone = state["rosters_by_slot"]["1"][0]
    bad = a_brief(available)
    bad.pick = B.Candidate(player_id=gone["player_id"], name=gone["name"],
                           pos=gone["pos"], why="Stale.")
    problems = B.validate_brief(bad, available)
    assert any("already drafted" in p for p in problems)
    assert gone["player_id"] in problems[0]


def test_an_unknown_player_id_is_refused(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    bad = a_brief(available)
    bad.pick = B.Candidate(player_id="not-a-player", name="Imaginary Man",
                           pos="RB", why="Invented.")
    assert any("not available" in p for p in B.validate_brief(bad, available))


def test_an_id_paired_with_the_wrong_name_is_refused(draft_artifacts):
    """Catches a real id stapled to a hallucinated name."""
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    row = next(iter(available.values()))
    bad = a_brief(available)
    bad.pick = B.Candidate(player_id=row["player_id"], name="Somebody Else",
                           pos=row["pos"], why="Mismatched.")
    problems = B.validate_brief(bad, available)
    assert any("is " + row["name"] in p for p in problems)


def test_a_kicker_or_defense_is_refused(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    row = next(iter(available.values()))
    bad = a_brief(available)
    bad.pick = B.Candidate(player_id=row["player_id"], name=row["name"],
                           pos="DST", why="No such slot exists.")
    assert any("no kicker or defense slot" in p for p in B.validate_brief(bad, available))


def test_the_alternative_has_to_be_a_different_player(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    bad = a_brief(available, first=0, second=0)
    assert any("the same player" in p for p in B.validate_brief(bad, available))


def test_a_bogus_watch_entry_is_refused(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    bad = a_brief(available, watch=["nope"])
    assert any("watch" in p for p in B.validate_brief(bad, available))


# --- the trigger -------------------------------------------------------------


def briefs_for(state, picks_made=None, available=None, status="ok"):
    """Twelve fresh, valid briefs, so a test only has to spoil the one it means."""
    rows = list((available or {}).values())
    rooms = {}
    for i, key in enumerate(sorted(state["war_rooms"], key=int)):
        room = {"slot": int(key), "name": state["war_rooms"][key]["name"], "status": status,
                "picks_made": state["picks_made"] if picks_made is None else picks_made,
                "strategy": "Standing plan."}
        if rows:
            room["pick"] = {"player_id": rows[i]["player_id"], "name": rows[i]["name"]}
        rooms[key] = room
    return {"rooms": rooms, "picks_made": state["picks_made"]}


def test_rooms_near_their_turn_and_the_team_that_just_picked_regenerate(draft_artifacts):
    board, state = league(draft_artifacts, 14)
    available = B.available_index(board, state)
    assert state["current_pick"] == 15

    targets = B.refresh_targets(state, briefs_for(state, available=available))
    # Under 3RR round 2 runs 12->1, so picks 15..18 belong to slots 10, 9, 8, 7.
    # Slot 11 made pick 14, so its roster just changed.
    assert targets == {7, 8, 9, 10, 11}


def test_a_room_with_no_brief_always_regenerates(draft_artifacts):
    _, state = league(draft_artifacts, 14)
    assert B.refresh_targets(state, {"rooms": {}}) == set(range(1, 13))


def test_a_room_whose_proposal_was_taken_regenerates(draft_artifacts):
    """The staleness that actually misleads: recommending someone already gone."""
    board, state = league(draft_artifacts, 14)
    available = B.available_index(board, state)
    briefs = briefs_for(state, available=available)
    gone = state["rosters_by_slot"]["1"][0]
    briefs["rooms"]["1"]["pick"] = {"player_id": gone["player_id"], "name": gone["name"]}
    assert 1 in B.refresh_targets(state, briefs)


def test_a_cold_room_refreshes_on_its_own_cadence(draft_artifacts):
    board, state = league(draft_artifacts, 14)
    available = B.available_index(board, state)
    briefs = briefs_for(state, available=available)
    assert 1 not in B.refresh_targets(state, briefs)
    briefs["rooms"]["1"]["picks_made"] = state["picks_made"] - B.COLD_EVERY
    assert 1 in B.refresh_targets(state, briefs)


def test_an_errored_room_is_retried(draft_artifacts):
    board, state = league(draft_artifacts, 14)
    available = B.available_index(board, state)
    briefs = briefs_for(state, available=available)
    briefs["rooms"]["2"]["status"] = "error"
    assert 2 in B.refresh_targets(state, briefs)


def test_refresh_all_regenerates_every_seat(draft_artifacts):
    board, state = league(draft_artifacts, 14)
    available = B.available_index(board, state)
    targets = B.refresh_targets(state, briefs_for(state, available=available), mode="all")
    assert targets == set(range(1, 13))


# --- the prompt --------------------------------------------------------------


def test_the_prompt_never_offers_a_drafted_player(draft_artifacts):
    board, state = league(draft_artifacts, 20)
    seat = live.team_state(state, 12)
    prompt = B.build_prompt(seat, state)
    for entry in state["rosters_by_slot"]["1"]:
        assert f"| {entry['player_id']} |" not in prompt
    for row in seat["best_available"]:
        assert f"| {row['player_id']} |" in prompt


def test_the_prompt_situates_the_seat(draft_artifacts):
    _, state = league(draft_artifacts, 20)
    seat = live.team_state(state, 12)
    prompt = B.build_prompt(seat, state)
    assert "Team L" in prompt
    assert f"pick {seat['survive_until_pick']} comes back to you" in prompt
    assert "PLAYBOOK D1" in prompt and "PLAYBOOK D2" in prompt


def test_the_league_block_is_marked_as_colour_not_an_urgency_input(draft_artifacts):
    """Twelve rooms reading each other's needs must not all reach a round early."""
    _, state = league(draft_artifacts, 20)
    prompt = B.build_prompt(live.team_state(state, 12), state)
    assert "context, not an urgency input" in prompt
    assert "Do not reach a round early because several rivals share a need." in prompt


def test_the_standing_plan_is_carried_forward(draft_artifacts):
    _, state = league(draft_artifacts, 20)
    seat = live.team_state(state, 12)
    previous = {"strategy": "Anchor RB then hammer WR.", "picks_made": 12}
    prompt = B.build_prompt(seat, state, previous)
    assert "Anchor RB then hammer WR." in prompt
    assert "Amend this rather than starting over" in prompt
    # With no previous brief there is nothing to amend.
    assert "standing plan" not in B.build_prompt(seat, state).lower()


# --- rendering ---------------------------------------------------------------


def test_a_room_renders_the_fields_a_reader_needs(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    seat = live.team_state(state, 3)
    room = B.new_room(seat, state, a_brief(available, watch=[next(iter(available))]),
                      model="claude-sonnet-5", available=available)
    md = B.render_brief_md(room)
    assert room["name"] in md
    assert room["pick"]["name"] in md and room["pick"]["player_id"] in md
    assert room["alternative"]["name"] in md
    assert "Anchor RB" in md
    assert "claude-sonnet-5" in md


def test_a_failed_room_says_so_rather_than_rendering_as_fresh(draft_artifacts):
    _, state = league(draft_artifacts, 10)
    seat = live.team_state(state, 3)
    room = B.new_room(seat, state, None, model="m", status="error", error="timed out")
    md = B.render_brief_md(room)
    assert "could not be regenerated" in md and "timed out" in md


def test_provenance_comes_from_code_not_the_model(draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    seat = live.team_state(state, 3)
    room = B.new_room(seat, state, a_brief(available), model="claude-sonnet-5",
                      available=available)
    assert room["slot"] == 3
    assert room["picks_made"] == state["picks_made"]
    assert room["for_pick"] == seat["my_next_pick"]
    assert room["status"] == "ok"
    assert room["generated_at"]


@pytest.mark.parametrize("count", [0, 14, 26])
def test_every_seat_can_be_prompted_at_any_point_in_the_draft(draft_artifacts, count):
    """Including before a pick is made and after the board has turned over."""
    _, state = league(draft_artifacts, count)
    for slot in range(1, 13):
        prompt = B.build_prompt(live.team_state(state, slot), state)
        assert prompt.startswith("# War room")
        assert "## Best available" in prompt


# --- the tools ---------------------------------------------------------------


def test_a_players_note_comes_back_whole_with_the_board_row(draft_artifacts):
    board, state = league(draft_artifacts, 5)
    available = B.available_index(board, state)
    read_player_note, board_rows = T.build_tools(board, available)

    with_note = next(r for r in board["players"] if r.get("research_note"))
    out = read_player_note(with_note["player_id"])
    assert with_note["name"] in out
    assert f"id {with_note['player_id']}" in out
    assert Path(with_note["research_note"]).read_text().strip()[:40] in out


def test_a_player_without_a_note_still_returns_the_board_row(draft_artifacts):
    board, state = league(draft_artifacts, 5)
    read_player_note, _ = T.build_tools(board, B.available_index(board, state))
    without = next(r for r in board["players"] if not r.get("research_note"))
    out = read_player_note(without["player_id"])
    assert "No research note" in out
    assert without["name"] in out


def test_an_unknown_id_gets_told_where_to_look(draft_artifacts):
    board, state = league(draft_artifacts, 5)
    read_player_note, _ = T.build_tools(board, B.available_index(board, state))
    assert "board_rows" in read_player_note("nope")


def test_board_rows_only_ever_returns_available_players(draft_artifacts):
    """The tool cannot hand back a drafted player, so the model cannot cite one."""
    board, state = league(draft_artifacts, 20)
    available = B.available_index(board, state)
    _, board_rows = T.build_tools(board, available)
    out = board_rows("ALL", 1, T.MAX_ROWS)
    for entry in state["rosters_by_slot"]["1"]:
        assert f"id {entry['player_id']}" not in out
    assert "id " in out


def test_board_rows_filters_by_position_and_caps_its_output(draft_artifacts):
    board, state = league(draft_artifacts, 5)
    _, board_rows = T.build_tools(board, B.available_index(board, state))
    out = board_rows("TE", 1, 99)
    lines = [ln for ln in out.splitlines() if ln.startswith("#")]
    assert lines and all("TE" in ln.split(" · ")[1] for ln in lines)
    assert len(lines) <= T.MAX_ROWS


def test_board_rows_says_so_when_nothing_matches(draft_artifacts):
    board, state = league(draft_artifacts, 5)
    _, board_rows = T.build_tools(board, B.available_index(board, state))
    assert "No available players match" in board_rows("QB", 999, 5)


# --- the prompt the live advisor and the war room share ----------------------


HARD_RULES = [
    "No kickers, no defenses.",
    "Those roster slots do not exist.",
    "Never recommend a player already drafted.",
    "Never invent a player.",
    "ADP is the market, not us.",
    "Do not re-derive rankings.",
]


def test_the_war_room_works_under_the_same_hard_rules_as_the_live_advisor():
    """Two prompts, one set of correctness rules. If one is edited alone this fails."""
    skill = Path(".claude/skills/draft-day/SKILL.md").read_text()
    instructions = (Path(A.INSTRUCTIONS)).read_text()
    for rule in HARD_RULES:
        assert rule in skill, f"SKILL.md no longer says: {rule}"
        assert rule in instructions, f"INSTRUCTIONS.md no longer says: {rule}"


def test_the_system_prompt_carries_the_doctrine():
    text = A.load_instructions(Path("draft/PLAYBOOK.md"))
    assert "# War room" in text
    assert "PLAYBOOK.md — the doctrine you draft by" in text
    assert "third-round" in text.lower()


def test_a_missing_playbook_is_survivable(tmp_path):
    """The framing alone is still a usable prompt."""
    text = A.load_instructions(tmp_path / "nope.md")
    assert "# War room" in text
    assert "the doctrine you draft by" not in text


# --- the runner --------------------------------------------------------------


def runner_args(tmp_path, **kw):
    import argparse
    base = dict(state_dir=tmp_path, board=Path("draft/board.json"),
                playbook=Path("draft/PLAYBOOK.md"), model="test-model", refresh="hot",
                slot=None, hot_within=B.HOT_WITHIN, cold_every=B.COLD_EVERY, timeout=5.0,
                concurrency=2, watch=False, interval=1.0, once=True, dry_run=True)
    base.update(kw)
    return argparse.Namespace(**base)


def test_briefs_are_written_atomically_and_leave_no_temp_files(tmp_path, draft_artifacts):
    board, state = league(draft_artifacts, 10)
    available = B.available_index(board, state)
    seat = live.team_state(state, 4)
    briefs = {"generated_at": "now", "picks_made": state["picks_made"], "model": "m",
              "rooms": {"4": B.new_room(seat, state, a_brief(available), model="m",
                                        available=available)}}
    R.write_briefs(briefs, tmp_path)
    R.write_briefs(briefs, tmp_path)

    assert json.loads((tmp_path / "briefs.json").read_text())["rooms"]["4"]["slot"] == 4
    assert "Anchor RB" in (tmp_path / "briefs.md").read_text()
    assert "Anchor RB" in (tmp_path / "teams" / "BRIEF-slot-4.md").read_text()
    assert not [f.name for f in tmp_path.rglob("*") if f.name.endswith(".tmp")]


def test_a_corrupt_briefs_file_starts_over_rather_than_refusing_to_run(tmp_path):
    """Briefs are regenerable; refusing to start mid-draft would be the wrong trade."""
    path = tmp_path / "briefs.json"
    path.write_text("{ not json")
    assert R.load_briefs(path) == {"rooms": {}}
    assert R.load_briefs(tmp_path / "absent.json") == {"rooms": {}}


def test_a_dry_run_writes_prompts_and_calls_nothing(tmp_path, draft_artifacts):
    board, state = league(draft_artifacts, 14)
    briefs = asyncio.run(R.run_cycle(state, board, {"rooms": {}}, runner_args(tmp_path)))
    written = sorted(f.name for f in (tmp_path / "prompts").iterdir())
    assert len(written) == 12          # no briefs yet, so every seat is a target
    assert briefs["rooms"] == {}       # and nothing was generated
    body = (tmp_path / "prompts" / "slot-12.md").read_text()
    assert body.startswith("# War room")


def test_only_one_seat_can_be_targeted(tmp_path, draft_artifacts):
    board, state = league(draft_artifacts, 14)
    asyncio.run(R.run_cycle(state, board, {"rooms": {}}, runner_args(tmp_path, slot=7)))
    assert [f.name for f in (tmp_path / "prompts").iterdir()] == ["slot-7.md"]


def test_an_env_file_fills_gaps_but_never_overrides_the_real_environment(tmp_path, monkeypatch):
    """A stale file must not quietly beat something the operator exported."""
    env = tmp_path / ".env"
    env.write_text('# a comment\n\nANTHROPIC_CHAT_MODEL="claude-from-file"\n'
                   "ALREADY_SET=from-file\nnot a pair\n")
    monkeypatch.setenv("ALREADY_SET", "from-shell")
    monkeypatch.delenv("ANTHROPIC_CHAT_MODEL", raising=False)

    assert R.load_env_file(env) == ["ANTHROPIC_CHAT_MODEL"]
    assert os.environ["ANTHROPIC_CHAT_MODEL"] == "claude-from-file"
    assert os.environ["ALREADY_SET"] == "from-shell"
    assert R.load_env_file(tmp_path / "absent") == []

from __future__ import annotations

import json
import sys

import pytest

from sleeper_draft import board
from sleeper_draft.client import SleeperError

# The real 12-team / 13-round third-round-reversal table, from FILE A3 of the
# research pack. Round 3 repeats round 2's direction; normal snake resumes at 4.
REAL_3RR = {
    "1": [1, 24, 36, 37, 60, 61, 84, 85, 108, 109, 132, 133, 156],
    "6": [6, 19, 31, 42, 55, 66, 79, 90, 103, 114, 127, 138, 151],
    "12": [12, 13, 25, 48, 49, 72, 73, 96, 97, 120, 121, 144, 145],
}


def run(args, players_cache):
    sys.argv = ["sleeper-board", "--cache-dir", str(players_cache), *args]
    return board.main()


def invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file,
           extra=()):
    out = tmp_path / "draft"
    run(["--rankings", str(rankings_file), "--notes-dir", str(notes_dir),
         "--config", str(league_config), "--scouting", str(scouting_file),
         "--out-dir", str(out), *extra], players_cache)
    return out


def test_normalize_name_folds_accents_punctuation_and_suffixes():
    assert board.normalize_name("Amon-Ra St. Brown") == "amonrastbrown"
    assert board.normalize_name("Ja'Marr Chase") == "jamarrchase"
    assert board.normalize_name("Chris Godwin Jr.") == board.normalize_name("Chris Godwin")
    assert board.normalize_name("Kyle Pitts Sr.") == board.normalize_name("Kyle Pitts")
    assert board.normalize_name("Oronde Gadsden II") == board.normalize_name("Oronde Gadsden")


def test_pick_numbers_match_the_real_3rr_table():
    picks = board.pick_numbers(teams=12, rounds=13, reversal_round=3)
    for slot, expected in REAL_3RR.items():
        assert picks[slot] == expected, f"slot {slot}"
    # Every overall pick is used exactly once.
    flat = sorted(n for slot_picks in picks.values() for n in slot_picks)
    assert flat == list(range(1, 12 * 13 + 1))


def test_pick_numbers_without_reversal_are_a_plain_snake():
    picks = board.pick_numbers(teams=12, rounds=4, reversal_round=None)
    assert picks["1"] == [1, 24, 25, 48]
    assert picks["12"] == [12, 13, 36, 37]


def test_reversal_round_outside_the_draft_errors():
    with pytest.raises(SleeperError, match="reversal_round=14"):
        board.pick_numbers(teams=12, rounds=13, reversal_round=14)


def test_verify_pick_numbers_rejects_a_disagreement(tmp_path):
    picks = board.pick_numbers(teams=12, rounds=13, reversal_round=3)
    bad = dict(REAL_3RR)
    bad["1"] = [1, 24, 25] + REAL_3RR["1"][3:]  # a plain snake's round 3
    with pytest.raises(SleeperError, match="Pick-order disagreement for draft slot 1"):
        board.verify_pick_numbers(picks, bad, tmp_path / "rankings.json")


def test_board_joins_every_ranking_row_to_a_player_id(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    doc = json.loads((out / "board.json").read_text())

    ranked = json.loads(rankings_file.read_text())["players"]
    assert doc["counts"]["ranked"] == len(ranked)
    assert [row["rank"] for row in doc["players"]] == sorted(row["rank"] for row in ranked)

    players = json.loads((players_cache / "players_nfl.json").read_text())
    for row in doc["players"]:
        assert players[row["player_id"]]["full_name"] == row["name"]
    # player_id is the join key, so it must be unique across the board.
    ids = [row["player_id"] for row in doc["players"]]
    assert len(set(ids)) == len(ids)


def test_unmatched_ranking_row_errors_and_names_it_and_writes_nothing(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(rankings_file.read_text())
    doc["players"][3]["name"] = "Nobody Whatsoever"
    rankings_file.write_text(json.dumps(doc))

    out = tmp_path / "draft"
    with pytest.raises(SleeperError) as exc:
        run(["--rankings", str(rankings_file), "--notes-dir", str(notes_dir),
             "--config", str(league_config), "--scouting", str(scouting_file),
             "--out-dir", str(out)], players_cache)
    assert "Nobody Whatsoever" in str(exc.value)
    assert "Nothing was written" in str(exc.value)
    assert not out.exists()


def test_ranked_player_without_a_research_note_is_kept_and_reported(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file,
        capsys):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    doc = json.loads((out / "board.json").read_text())

    # The notes_dir fixture deliberately omits the last ranked player.
    without = [row for row in doc["players"] if row["research_note"] is None]
    assert len(without) == 1
    assert without[0]["rank"] == doc["counts"]["ranked"]
    assert doc["counts"]["ranked_with_research_note"] == doc["counts"]["ranked"] - 1
    assert without[0]["name"] in capsys.readouterr().err

    md = (out / "board.md").read_text()
    assert "_no research note_" in md


def test_research_note_for_an_unranked_player_lands_in_the_extras_bin(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    players = json.loads((players_cache / "players_nfl.json").read_text())
    ranked = {row["name"] for row in json.loads(rankings_file.read_text())["players"]}
    pid, player = next((pid, p) for pid, p in sorted(players.items())
                       if p.get("full_name") and p["full_name"] not in ranked
                       and p.get("position") in ("QB", "RB", "WR", "TE"))
    (notes_dir / f"stub-{player['position']}-{pid}.md").write_text("## unranked\n")

    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    doc = json.loads((out / "board.json").read_text())
    assert [e["player_id"] for e in doc["researched_unranked"]] == [pid]
    assert player["full_name"] in (out / "board.md").read_text()


def test_risk_flag_is_attached_to_the_flagged_player(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    doc = json.loads((out / "board.json").read_text())
    flagged = [row for row in doc["players"] if row["risk_flag"]]
    assert len(flagged) == 1
    assert flagged[0]["rank"] == 1
    assert "Test flag" in (out / "board.md").read_text()


def test_kicker_or_defense_in_the_rankings_is_rejected(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(rankings_file.read_text())
    doc["players"][0]["pos"] = "K"
    rankings_file.write_text(json.dumps(doc))
    with pytest.raises(SleeperError, match="no kicker or defense slots"):
        invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)


def test_ranking_row_missing_a_required_field_is_rejected(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(rankings_file.read_text())
    del doc["players"][2]["tier"]
    rankings_file.write_text(json.dumps(doc))
    with pytest.raises(SleeperError, match="is missing tier"):
        invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)


def test_note_filename_without_a_player_id_is_rejected(notes_dir):
    (notes_dir / "no-join-key.md").write_text("## orphan\n")
    with pytest.raises(SleeperError, match="does not match"):
        board.index_notes(notes_dir)


def test_two_notes_claiming_one_player_id_are_rejected(notes_dir):
    existing = sorted(notes_dir.glob("*.md"))[0]
    pid = existing.name.rsplit("-", 1)[-1][:-3]
    (notes_dir / f"other-WR-{pid}.md").write_text("## duplicate\n")
    with pytest.raises(SleeperError, match=f"player_id {pid}"):
        board.index_notes(notes_dir)


def test_pick_order_file_covers_every_pick(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    order = json.loads((out / "pick_order.json").read_text())
    assert order["picks_by_slot"]["12"] == REAL_3RR["12"]
    assert len(order["slot_by_pick"]) == 12 * 13
    assert order["slot_by_pick"]["25"] == 12  # round 3 opens with the back of the order


def test_board_md_is_grouped_by_tier_and_carries_the_join_key(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    md = (out / "board.md").read_text()
    doc = json.loads((out / "board.json").read_text())
    for tier in sorted({row["tier"] for row in doc["players"]}):
        assert f"## Tier {tier} —" in md
    assert "no K, no DST" in md
    for row in doc["players"]:
        assert f"| {row['player_id']} |" in md


def test_scouting_notes_merge_onto_the_right_rows(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    doc = json.loads((out / "board.json").read_text())
    rows = {row["rank"]: row for row in doc["players"]}

    assert rows[1]["scouting"] == "workhorse"
    assert rows[1]["flags"] == ["value"]
    assert rows[2]["handcuff_for"] == rows[1]["player_id"]
    assert rows[2]["handcuff_for_name"] == rows[1]["name"]
    assert rows[3]["tier_label"] == "dead zone R5-7"
    assert doc["counts"]["with_scouting_note"] == 3

    # A player with no scouting entry keeps empty defaults, not nulls that break rendering.
    assert rows[4]["scouting"] is None
    assert rows[4]["flags"] == []
    assert rows[4]["handcuff_for"] is None


def test_scouting_renders_in_board_md(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    md = (out / "board.md").read_text()
    doc = json.loads((out / "board.json").read_text())
    starter = next(row for row in doc["players"] if row["rank"] == 1)

    assert "`value`" in md
    assert "workhorse" in md
    assert f"✂️ handcuff for {starter['name']}" in md
    assert "_dead zone R5-7_" in md


def test_scouting_note_for_an_unknown_player_id_errors_and_writes_nothing(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(scouting_file.read_text())
    doc["notes"]["not-a-real-player"] = {"text": "ghost"}
    scouting_file.write_text(json.dumps(doc))

    out = tmp_path / "draft"
    with pytest.raises(SleeperError) as exc:
        run(["--rankings", str(rankings_file), "--notes-dir", str(notes_dir),
             "--config", str(league_config), "--scouting", str(scouting_file),
             "--out-dir", str(out)], players_cache)
    assert "not-a-real-player" in str(exc.value)
    assert "Nothing was written" in str(exc.value)
    assert not out.exists()


def test_dangling_handcuff_for_errors(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(scouting_file.read_text())
    pid = next(iter(doc["notes"]))
    doc["notes"][pid]["handcuff_for"] = "9999999999"
    scouting_file.write_text(json.dumps(doc))
    with pytest.raises(SleeperError, match="handcuff_for link"):
        invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)


def test_unknown_scouting_flag_errors_and_names_it(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(scouting_file.read_text())
    pid = next(iter(doc["notes"]))
    doc["notes"][pid]["flags"] = ["sleeper-pick"]
    scouting_file.write_text(json.dumps(doc))
    with pytest.raises(SleeperError, match="sleeper-pick"):
        invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)


def test_missing_scouting_file_errors(
        tmp_path, players_cache, rankings_file, notes_dir, league_config):
    with pytest.raises(SleeperError, match="does not exist"):
        invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config,
               tmp_path / "absent.json")


def test_board_md_carries_the_rankings_provenance(
        tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file):
    doc = json.loads(rankings_file.read_text())
    doc["meta"]["player_pool"] = "QB/RB/WR/TE only"
    doc["meta"]["method"] = "blended on weights"
    doc["meta"]["sources"] = [{"name": "Test ADP", "date": "2026-09-05", "weight": 0.45,
                              "why": "format match"}]
    doc["draft_mechanics"]["explanation"] = "round 3 repeats round 2"
    rankings_file.write_text(json.dumps(doc))

    out = invoke(tmp_path, players_cache, rankings_file, notes_dir, league_config, scouting_file)
    md = (out / "board.md").read_text()
    assert "## Provenance" in md
    for expected in ("QB/RB/WR/TE only", "blended on weights", "Test ADP", "format match",
                     "round 3 repeats round 2"):
        assert expected in md
    source = json.loads((out / "board.json").read_text())["source"]
    assert source["sources"][0]["name"] == "Test ADP"
    assert source["draft_mechanics"] == "round 3 repeats round 2"

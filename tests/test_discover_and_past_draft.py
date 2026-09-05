from __future__ import annotations

import json
import sys

import pytest
import yaml

from sleeper_draft import discover, past_draft
from sleeper_draft.client import SleeperError


def run_discover(args):
    sys.argv = ["sleeper-discover", *args]
    return discover.main()


def run_past_draft(args):
    sys.argv = ["sleeper-past-draft", *args]
    return past_draft.main()


# ------------------------------------------------------------------ discover


def test_league_id_alone_is_enough(tmp_path, stub_client, capsys):
    out = tmp_path / "config.yaml"
    run_discover(["--league-id", "L2026", "--out", str(out)])
    config = yaml.safe_load(out.read_text())

    assert config["league_id"] == "L2026"
    assert config["draft_id"] == "D2026"
    assert config["rounds"] == 14
    assert config["teams"] == 12
    assert config["reversal_round"] == 3
    assert config["previous_league_id"] == "L2025"
    assert config["season"] == "2026"          # taken from the league itself
    assert config["slot_to_roster_id"]["1"] == 1
    assert "rec" in config["scoring_settings"]
    assert config["user_id"] is None           # no user lookup happened


def test_username_path_lists_leagues(stub_client, capsys):
    run_discover(["--username", "me", "--season", "2026"])
    out = capsys.readouterr().out
    assert "user_id: U1" in out
    assert "L2026" in out
    assert "auto-selected" in out


def test_missing_reversal_round_is_reported_not_assumed(stub_client, capsys):
    run_discover(["--league-id", "L2024"])
    out = capsys.readouterr().out
    assert "no 'reversal_round' key" in out
    assert yaml.safe_load(out.split("paste below into your config ----------")[1]
                          .split("# ---------- end")[0])["reversal_round"] is None


def test_unknown_league_errors(stub_client):
    with pytest.raises(SleeperError, match="null body"):
        run_discover(["--league-id", "NOPE"])


def test_no_args_at_all_exits_two(stub_client):
    with pytest.raises(SystemExit) as exc:
        run_discover([])
    assert exc.value.code == 2


# --------------------------------------------------------------- past_draft


def test_walks_back_one_season(tmp_path, stub_client):
    out = tmp_path / "fixture.json"
    run_past_draft(["--league-id", "L2026", "--back", "1", "--out", str(out)])
    fixture = json.loads(out.read_text())

    assert fixture["league"]["season"] == "2025"
    assert fixture["draft"]["draft_id"] == "D2025"
    assert fixture["pick_count"] == 168
    assert fixture["expected_pick_count"] == 168
    assert [c["season"] for c in fixture["chain"]] == ["2026", "2025"]
    assert fixture["picks"][0]["pick_no"] == 1
    assert fixture["draft"]["slot_to_roster_id"]["1"] == 1


def test_walk_to_named_season(tmp_path, stub_client):
    with pytest.raises(SleeperError, match="zero picks"):
        run_past_draft(["--league-id", "L2026", "--season", "2024",
                        "--out", str(tmp_path / "f.json")])


def test_chain_too_short_names_where_it_stopped(tmp_path, stub_client):
    with pytest.raises(SleeperError) as exc:
        run_past_draft(["--league-id", "L2026", "--back", "5", "--out", str(tmp_path / "f.json")])
    assert "no previous_league_id" in str(exc.value)
    assert "2024:L2024" in str(exc.value)

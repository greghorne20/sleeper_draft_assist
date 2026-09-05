from __future__ import annotations

import json

import pytest
import yaml

from sleeper_draft import batches
from sleeper_draft.client import SleeperError


def run(args, players_cache):
    batches.main.__globals__  # noqa: B018 - keep import graph explicit
    import sys

    sys.argv = ["sleeper-batches", "--cache-dir", str(players_cache), *args]
    return batches.main()


def test_writes_expected_batches(tmp_path, players_cache, byes_file):
    out = tmp_path / "research" / "batches"
    run(["--byes", str(byes_file), "--out-dir", str(out)], players_cache)

    files = sorted(out.glob("*.yaml"))
    assert len(files) == 8  # 220 / 35 = 7 skill files, plus one K/DEF file
    assert files[-1].name.endswith("_k_def.yaml")

    total = 0
    for path in files:
        doc = yaml.safe_load(path.read_text())
        assert doc["count"] == len(doc["players"])
        # Defenses have a null search_rank (Sleeper never ranks them), which sorts
        # to the end; every other row carries an int. Normalize null to a sentinel
        # so the ordering check mirrors the code's own sort key.
        ranks = [p["search_rank"] if p["search_rank"] is not None else 9999999
                 for p in doc["players"]]
        assert ranks == sorted(ranks), f"{path} is not in search_rank order"
        for player in doc["players"]:
            assert set(player) == {"player_id", "name", "pos", "team", "bye", "search_rank"}
            assert isinstance(player["bye"], int)
            assert isinstance(player["player_id"], str)
        total += doc["count"]
    assert total == 220 + 24


def test_excludes_junk_rows(tmp_path, players_cache, byes_file):
    out = tmp_path / "b"
    run(["--byes", str(byes_file), "--out-dir", str(out)], players_cache)
    names = {
        p["name"]
        for path in out.glob("*.yaml")
        for p in yaml.safe_load(path.read_text())["players"]
    }
    assert "Sentinel Guy" not in names   # search_rank 9999999
    assert "Free Agent" not in names     # team is null
    assert "Duplicate Player" not in names  # inactive, null positions


def test_defense_name_falls_back_to_first_last(tmp_path, players_cache, byes_file):
    out = tmp_path / "b"
    run(["--byes", str(byes_file), "--out-dir", str(out)], players_cache)
    kdef = yaml.safe_load(sorted(out.glob("*_k_def.yaml"))[0].read_text())
    defenses = [p for p in kdef["players"] if p["pos"] == "DEF"]
    assert defenses, "expected defenses in the final batch"
    assert all(p["name"].endswith(" Defense") for p in defenses)


def test_team_no_survives_yaml_roundtrip(tmp_path, players_cache, byes_file):
    """Bare YAML 1.1 reads NO as false. Make sure it comes back as a string."""
    out = tmp_path / "b"
    run(["--byes", str(byes_file), "--out-dir", str(out)], players_cache)
    teams = {
        p["team"]
        for path in out.glob("*.yaml")
        for p in yaml.safe_load(path.read_text())["players"]
    }
    assert "NO" in teams
    assert False not in teams


def test_missing_bye_team_errors_and_names_it(tmp_path, players_cache, byes_file):
    partial = json.loads(byes_file.read_text())
    partial.pop("KC")
    partial.pop("SF")
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(partial))

    with pytest.raises(SleeperError) as exc:
        run(["--byes", str(path), "--out-dir", str(tmp_path / "b")], players_cache)
    assert "KC" in str(exc.value)
    assert "SF" in str(exc.value)
    assert not list((tmp_path / "b").glob("*.yaml")) if (tmp_path / "b").exists() else True


def test_placeholder_zero_bye_is_rejected(tmp_path, players_cache):
    path = tmp_path / "byes.json"
    path.write_text(json.dumps({"ARI": 0}))
    with pytest.raises(SleeperError, match="outside weeks 1-22"):
        run(["--byes", str(path), "--out-dir", str(tmp_path / "b")], players_cache)


def test_missing_bye_file_errors(tmp_path, players_cache):
    with pytest.raises(SleeperError, match="does not exist"):
        run(["--byes", str(tmp_path / "nope.json"), "--out-dir", str(tmp_path / "b")], players_cache)


def test_limit_larger_than_pool_errors(tmp_path, players_cache, byes_file):
    with pytest.raises(SleeperError, match="but 5000 were requested"):
        run(["--byes", str(byes_file), "--limit", "5000", "--out-dir", str(tmp_path / "b")],
            players_cache)

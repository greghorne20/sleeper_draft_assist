from __future__ import annotations

import json
import time

import pytest

from sleeper_draft.client import SleeperClient, SleeperError


def test_fresh_cache_is_reused_without_http(players_cache):
    client = SleeperClient(cache_dir=players_cache)
    client._get = lambda path: pytest.fail(f"unexpected HTTP call to {path}")
    players = client.get_players()
    assert len(players) > 600
    assert client.players_cache_age_hours() < 1


def test_stale_cache_triggers_refetch(players_cache):
    meta = json.loads((players_cache / "players_nfl.meta.json").read_text())
    meta["fetched_at"] = time.time() - 60 * 60 * 48  # two days old
    (players_cache / "players_nfl.meta.json").write_text(json.dumps(meta))

    client = SleeperClient(cache_dir=players_cache)
    calls = []
    client._get = lambda path: (calls.append(path), {"1": {"player_id": "1"}})[1]

    assert client.get_players() == {"1": {"player_id": "1"}}
    assert calls == ["/players/nfl"]
    assert client.players_cache_age_hours() < 1  # cache was rewritten


def test_missing_cache_reports_no_age(tmp_path):
    assert SleeperClient(cache_dir=tmp_path / "empty").players_cache_age_hours() is None


def test_corrupt_cache_errors_loudly(players_cache):
    (players_cache / "players_nfl.json").write_text("{not json")
    with pytest.raises(SleeperError, match="corrupt"):
        SleeperClient(cache_dir=players_cache).get_players()


def test_user_without_user_id_errors(tmp_path):
    client = SleeperClient(cache_dir=tmp_path)
    client._get = lambda path: {"username": "x"}
    with pytest.raises(SleeperError, match="no 'user_id' field"):
        client.get_user("x")

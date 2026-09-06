from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import pytest
from conftest import make_picks

from sleeper_draft import live, serve
from sleeper_draft.client import SleeperError

DRAFT = {"draft_id": "D2026", "status": "drafting", "draft_order": {}}


@pytest.fixture
def server(tmp_path):
    """A server on an ephemeral port, so tests never collide with a real one."""
    out = tmp_path / "state"
    out.mkdir()
    srv = serve.serve_in_background(out, "127.0.0.1", 0)
    yield srv, out
    srv.shutdown()
    srv.server_close()


def get(srv, path):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    try:
        with urllib.request.urlopen(url, timeout=5) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def write_state(out, draft_artifacts, count=12):
    board = json.loads((draft_artifacts / "board.json").read_text())
    order = json.loads((draft_artifacts / "pick_order.json").read_text())
    state = live.summarize(board, order, DRAFT, make_picks(order, board, count), 12, 4, 30)
    live.write_state(state, out)
    return state


def test_root_serves_the_page(server):
    srv, _ = server
    status, headers, body = get(srv, "/")
    assert status == 200
    assert headers["Content-Type"] == "text/html; charset=utf-8"
    assert body == serve.ASSET.read_bytes()
    assert b"<title>Draft Room</title>" in body


def test_index_html_is_the_same_page(server):
    srv, _ = server
    assert get(srv, "/index.html")[2] == get(srv, "/")[2]


def test_state_json_is_served_and_must_not_be_cached(server, draft_artifacts):
    srv, out = server
    state = write_state(out, draft_artifacts)
    status, headers, body = get(srv, "/state.json")

    assert status == 200
    assert headers["Content-Type"] == "application/json"
    # Without no-store the browser serves a stale copy and the page silently
    # freezes mid-draft while looking healthy.
    assert headers["Cache-Control"] == "no-store"
    assert json.loads(body)["picks_made"] == state["picks_made"]


def test_state_before_the_first_poll_is_a_json_404_not_a_crash(server):
    srv, _ = server
    status, headers, body = get(srv, "/state.json")
    assert status == 404
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body)["error"] == "no state yet"


def test_query_string_still_resolves_the_route(server, draft_artifacts):
    srv, out = server
    write_state(out, draft_artifacts)
    assert get(srv, "/state.json?cachebust=123")[0] == 200


def test_unknown_route_404s(server):
    srv, _ = server
    assert get(srv, "/nope")[0] == 404


@pytest.mark.parametrize("path", [
    "/../../../etc/passwd",
    "/..%2f..%2f..%2fetc%2fpasswd",
    "/state.json/../../../etc/passwd",
    "/board.json",
])
def test_no_path_traversal(server, path):
    """Only two literal routes exist, so nothing else can be reached at all."""
    srv, _ = server
    status, _, body = get(srv, path)
    assert status == 404
    assert b"root:" not in body


def test_request_logging_is_silenced(server, capsys):
    srv, _ = server
    get(srv, "/")
    assert "GET" not in capsys.readouterr().err


def test_a_port_already_in_use_is_a_clear_error(server, tmp_path):
    srv, _ = server
    taken = srv.server_address[1]
    with pytest.raises(SleeperError, match=f"127.0.0.1:{taken}"):
        serve.serve_in_background(tmp_path, "127.0.0.1", taken)


def test_page_only_reads_fields_the_state_actually_has(draft_artifacts, tmp_path):
    """Schema-drift guard: fails the moment the page binds to a dropped field."""
    state = write_state(tmp_path, draft_artifacts)
    html = serve.ASSET.read_text()
    referenced = set(re.findall(r"\bs\.([a-z_]+)", html))
    assert referenced, "expected the page to read state fields"
    missing = sorted(referenced - set(state))
    assert not missing, f"page reads fields absent from state.json: {missing}"


def test_page_reads_only_projected_player_fields(draft_artifacts, tmp_path):
    """Same guard for the per-player rows the display projection narrowed."""
    state = write_state(tmp_path, draft_artifacts)
    html = serve.ASSET.read_text()
    referenced = set(re.findall(r"\bp\.([a-z_]+)", html))
    allowed = set(live.DISPLAY_FIELDS) | {"adp", "leaving"} | set(state["my_roster"][0]) \
        | set(state["recent_picks"][0])
    missing = sorted(referenced - allowed)
    assert not missing, f"page reads player fields nothing emits: {missing}"


def test_page_has_an_anchor_for_every_section():
    html = serve.ASSET.read_text()
    for anchor in ("at-risk", "best-available", "tiers", "roster", "recent", "stale"):
        assert f'id="{anchor}"' in html, anchor

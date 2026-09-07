from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import pytest
from conftest import make_picks

from sleeper_draft import live, serve
from sleeper_draft.client import SleeperError
from sleeper_draft.warroom import brief as B

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


def get(srv, path, headers=None):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


MY_SLOT = 12


def write_state(out, draft_artifacts, count=12):
    """What the poller actually writes now: the whole league in one file."""
    board = json.loads((draft_artifacts / "board.json").read_text())
    order = json.loads((draft_artifacts / "pick_order.json").read_text())
    state = live.summarize_all(
        board, order, DRAFT, make_picks(order, board, count), 4, 30, {3: "Comeback Kids"}, MY_SLOT
    )
    live.write_all_state(state, out, MY_SLOT)
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
    # A browser that serves a stale copy without asking freezes the page
    # mid-draft while it looks healthy. no-cache forbids that just as no-store
    # does -- it only also permits the answer to be "unchanged".
    assert headers["Cache-Control"] == "no-cache"
    assert headers["ETag"]
    assert json.loads(body)["picks_made"] == state["picks_made"]


@pytest.mark.parametrize("route,name", [("/state.json", "state.json"), ("/briefs.json", "briefs.json")])
def test_a_file_that_has_not_been_written_is_a_json_404_not_a_crash(server, route, name):
    """The poller may not have finished, and sleeper-warroom may never run at all."""
    srv, _ = server
    status, headers, body = get(srv, route)
    assert status == 404
    assert headers["Content-Type"] == "application/json"
    assert json.loads(body)["error"] == f"no {name} yet"


def test_briefs_are_served_and_must_not_be_cached(server, draft_artifacts):
    srv, out = server
    write_state(out, draft_artifacts)
    out.joinpath("briefs.json").write_text(json.dumps({"rooms": {"12": {"slot": 12}}}))
    status, headers, body = get(srv, "/briefs.json")
    assert status == 200
    assert headers["Content-Type"] == "application/json"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["ETag"]
    assert json.loads(body)["rooms"]["12"]["slot"] == 12


def test_an_unchanged_state_answers_304_with_no_body(server, draft_artifacts):
    """The page polls once a second; this is what makes that cost nothing."""
    srv, out = server
    write_state(out, draft_artifacts)
    _, headers, first = get(srv, "/state.json")
    etag = headers["ETag"]

    status, headers, body = get(srv, "/state.json", {"If-None-Match": etag})
    assert status == 304
    assert body == b""
    assert headers["ETag"] == etag
    assert headers["Cache-Control"] == "no-cache"


def test_a_changed_state_is_never_answered_304(server, draft_artifacts):
    """The failure that matters is the opposite one: a stale board looking live."""
    srv, out = server
    write_state(out, draft_artifacts, count=12)
    etag = get(srv, "/state.json")[1]["ETag"]

    write_state(out, draft_artifacts, count=13)
    status, headers, body = get(srv, "/state.json", {"If-None-Match": etag})
    assert status == 200
    assert headers["ETag"] != etag
    assert json.loads(body)["picks_made"] == 13


def test_the_board_does_not_depend_on_briefs_existing(server, draft_artifacts):
    """The agent layer is optional; the state route must not care whether it ran."""
    srv, out = server
    write_state(out, draft_artifacts)
    assert get(srv, "/briefs.json")[0] == 404
    assert get(srv, "/state.json")[0] == 200


def test_query_string_still_resolves_the_route(server, draft_artifacts):
    srv, out = server
    write_state(out, draft_artifacts)
    assert get(srv, "/state.json?cachebust=123")[0] == 200


def test_unknown_route_404s(server):
    srv, _ = server
    assert get(srv, "/nope")[0] == 404


@pytest.mark.parametrize(
    "path",
    [
        "/../../../etc/passwd",
        "/..%2f..%2f..%2fetc%2fpasswd",
        "/state.json/../../../etc/passwd",
        "/board.json",
    ],
)
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
    """Schema-drift guard: fails the moment the page binds to a dropped field.

    The page reads three shapes and names each one, so each gets its own guard:
    `lg` is the league state as written, `rm` one war-room block, and `s` the
    seat projection the renderers take.
    """
    state = write_state(tmp_path, draft_artifacts)
    html = serve.ASSET.read_text()

    seat = live.team_state(state, MY_SLOT)
    referenced = set(re.findall(r"\bs\.([a-z_]+)", html))
    assert referenced, "expected the page to read state fields"
    missing = sorted(referenced - set(seat))
    assert not missing, f"page reads seat fields absent from the projection: {missing}"

    referenced = set(re.findall(r"\blg\.([a-z_]+)", html))
    assert referenced, "expected the page to read league fields"
    missing = sorted(referenced - set(state))
    assert not missing, f"page reads fields absent from state.json: {missing}"

    referenced = set(re.findall(r"\brm\.([a-z_]+)", html))
    assert referenced, "expected the page to read war-room fields"
    missing = sorted(referenced - set(state["war_rooms"][str(MY_SLOT)]))
    assert not missing, f"page reads war-room fields nothing emits: {missing}"


def test_page_only_reads_brief_fields_the_war_room_emits(draft_artifacts, tmp_path):
    """Fourth shape: `b.` is one room's brief, as sleeper-warroom writes it."""
    board = json.loads((draft_artifacts / "board.json").read_text())
    order = json.loads((draft_artifacts / "pick_order.json").read_text())
    state = live.summarize_all(board, order, DRAFT, make_picks(order, board, 12), 4, 30, None, MY_SLOT)
    available = B.available_index(board, state)
    rows = list(available.values())
    written = B.Brief(
        strategy="Plan.",
        pick=B.Candidate(
            player_id=rows[0]["player_id"], name=rows[0]["name"], pos=rows[0]["pos"], why="Because."
        ),
        alternative=B.Candidate(
            player_id=rows[1]["player_id"], name=rows[1]["name"], pos=rows[1]["pos"], why="Or this."
        ),
        watch=[rows[2]["player_id"]],
        risks=["A risk."],
    )
    room = B.new_room(live.team_state(state, MY_SLOT), state, written, model="m", available=available)

    html = serve.ASSET.read_text()
    referenced = set(re.findall(r"\bb\.([a-z_]+)", html))
    assert referenced, "expected the page to read brief fields"
    missing = sorted(referenced - set(room))
    assert not missing, f"page reads brief fields the war room never writes: {missing}"


def test_page_reads_only_projected_player_fields(draft_artifacts, tmp_path):
    """Same guard for the per-player rows the display projection narrowed."""
    state = write_state(tmp_path, draft_artifacts)
    seat = live.team_state(state, MY_SLOT)
    html = serve.ASSET.read_text()
    referenced = set(re.findall(r"\bp\.([a-z_]+)", html))
    allowed = (
        set(live.DISPLAY_FIELDS)
        | {"adp", "leaving"}
        | set(seat["my_roster"][0])
        | set(seat["recent_picks"][0])
    )
    missing = sorted(referenced - allowed)
    assert not missing, f"page reads player fields nothing emits: {missing}"


def test_page_has_a_room_for_every_seat(draft_artifacts, tmp_path):
    """The strip is the only way to reach the other eleven, so it must list them."""
    state = write_state(tmp_path, draft_artifacts)
    assert len(state["war_rooms"]) == 12
    html = serve.ASSET.read_text()
    assert 'id="rooms"' in html and 'id="league"' in html
    # Seats are switched by hash so a war room can bookmark its own view.
    assert "slot=${btn.dataset.slot}" in html
    assert "hashchange" in html


def test_page_has_an_anchor_for_every_section():
    html = serve.ASSET.read_text()
    for anchor in ("at-risk", "best-available", "tiers", "roster", "recent", "stale", "rooms", "league"):
        assert f'id="{anchor}"' in html, anchor

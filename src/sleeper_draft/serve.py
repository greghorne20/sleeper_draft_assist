#!/usr/bin/env python3
"""Serve the live draft page and the state file it reads.

Three literal routes and nothing else:

    /            live_view.html, packaged next to this module
    /state.json  <out-dir>/state.json, written by the poll loop
    /briefs.json <out-dir>/briefs.json, written by sleeper-warroom if it is running

The poll loop and the server share nothing but the filesystem: the loop writes
files, the server reads them. No locks, no shared mutable state, no coupling
beyond a directory path.

WHY NOT SimpleHTTPRequestHandler
    Because it maps request paths onto a directory, which means every request is
    a path-traversal question. This handler matches a fixed set of literal strings and never
    joins a request path to anything, so traversal is impossible by construction
    rather than by sanitising.

WHY no-cache RATHER THAN no-store
    Both forbid serving a cached copy without asking, which is the property that
    matters: a browser quietly serving a stale state.json freezes the page
    mid-draft while it looks perfectly healthy, the worst failure this tool could
    have. `no-store` also forbids *keeping* the copy, which means the browser has
    nothing to revalidate against and every poll re-downloads the whole file.
    `no-cache` keeps the copy and revalidates it on every single request, so an
    unchanged state answers 304 with no body. The page polls once a second and
    state.json is ~42KB; across twelve war rooms that is the difference between
    ~840KB/s and nothing at all, and it is what makes polling that fast cheap
    enough to be the right answer to "why is the clock a second behind".
"""

from __future__ import annotations

import hashlib
import json
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

from .client import SleeperError

ASSET = Path(__file__).parent / "live_view.html"

PAGE_ROUTES = ("/", "/index.html")

# Route -> the literal filename it serves. Both halves are constants: the request
# path is matched against a fixed key and the filename comes from this table, so
# nothing the client sends is ever joined to a directory.
JSON_ROUTES = {"/state.json": "state.json", "/briefs.json": "briefs.json"}


class StateHandler(BaseHTTPRequestHandler):
    """Serves the page and the state file. `out_dir` is bound via functools.partial."""

    protocol_version = "HTTP/1.1"

    def __init__(self, *args: Any, out_dir: Path, **kwargs: Any) -> None:
        self.out_dir = out_dir
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002
        """Silence per-request logging -- it would bury the poll output."""

    def _send(
        self, status: int, body: bytes, content_type: str, revalidate: bool = False, etag: str | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if revalidate:
            self.send_header("Cache-Control", "no-cache")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def _send_304(self, etag: str) -> None:
        """An unchanged state. No body, by definition of the status."""
        self.send_response(304)
        self.send_header("Cache-Control", "no-cache")
        self.send_header("ETag", etag)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's own naming
        route = self.path.split("?", 1)[0]

        if route in PAGE_ROUTES:
            if not ASSET.exists():
                self._send(500, b"live_view.html is missing from the package", "text/plain; charset=utf-8")
                return
            self._send(200, ASSET.read_bytes(), "text/html; charset=utf-8")
            return

        filename = JSON_ROUTES.get(route)
        if filename:
            path = self.out_dir / filename
            if not path.exists():
                # The server can be up before the first poll finishes, and briefs
                # may never arrive at all -- sleeper-warroom is optional. Say so in
                # JSON so the page can render "waiting" or hide a panel rather than
                # treating either as an error.
                self._send(
                    404,
                    json.dumps(
                        {"error": f"no {filename} yet", "detail": "waiting for the first write"}
                    ).encode(),
                    "application/json",
                    revalidate=True,
                )
                return
            # Hashed rather than derived from mtime and size: the whole point of
            # this route is that the page must never be told "unchanged" about a
            # state that changed, and a poll landing inside one filesystem
            # timestamp is not a risk worth reasoning about. The file is read
            # either way; only the body on the wire is saved.
            body = path.read_bytes()
            etag = f'"{hashlib.blake2b(body, digest_size=12).hexdigest()}"'
            if self.headers.get("If-None-Match") == etag:
                self._send_304(etag)
                return
            self._send(200, body, "application/json", revalidate=True, etag=etag)
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


def serve_in_background(out_dir: Path, host: str, port: int) -> ThreadingHTTPServer:
    """Start the server on a daemon thread and return it.

    Port 0 asks the OS for an ephemeral port; read the real one back off
    `server.server_address[1]`.
    """
    handler = partial(StateHandler, out_dir=Path(out_dir))
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise SleeperError(
            f"Cannot serve on {host}:{port} -- {exc}. Something else is probably using that "
            "port; pass --port to pick another."
        ) from exc
    server.daemon_threads = True
    Thread(target=server.serve_forever, name="sleeper-live-http", daemon=True).start()
    return server

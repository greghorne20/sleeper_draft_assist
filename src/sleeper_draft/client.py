"""Thin, read-only wrapper over the Sleeper API.

Standard library only. No writes to Sleeper, no scraping, no HTML parsing.

Endpoints covered (base https://api.sleeper.app/v1):
    GET /user/{username_or_id}
    GET /user/{user_id}/leagues/{sport}/{season}
    GET /league/{league_id}
    GET /league/{league_id}/drafts
    GET /draft/{draft_id}
    GET /draft/{draft_id}/picks
    GET /players/{sport}          (cached on disk, refreshed at most once a day)

Design notes:
  * Every failure raises. Nothing is swallowed, nothing is defaulted.
  * The players dump is ~5MB. It is cached to disk and re-fetched only when the
    cache is older than `players_max_age_hours` (default 24) or --refresh-players
    is passed by a caller.
  * A small floor on inter-request spacing keeps us far under Sleeper's
    1000 calls/min guidance.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://api.sleeper.app/v1"
DEFAULT_CACHE_DIR = Path(os.environ.get("SLEEPER_CACHE_DIR", ".cache/sleeper"))
USER_AGENT = "personal-draft-assistant/1.0 (single-user, read-only)"


class SleeperError(RuntimeError):
    """Any failure talking to Sleeper, or any unusable response."""


class SleeperHTTPError(SleeperError):
    def __init__(self, url: str, status: int, body: str) -> None:
        super().__init__(f"HTTP {status} from {url}\n{body[:500]}")
        self.url = url
        self.status = status
        self.body = body


class SleeperClient:
    def __init__(
        self,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        timeout: float = 30.0,
        min_interval_s: float = 0.10,
        players_max_age_hours: float = 24.0,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.min_interval_s = min_interval_s
        self.players_max_age_hours = players_max_age_hours
        self._last_request_at = 0.0

    # ---------------------------------------------------------------- HTTP

    def _get(self, path: str) -> Any:
        url = f"{BASE_URL}{path}"

        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise SleeperHTTPError(url, exc.code, body) from exc
        except urllib.error.URLError as exc:
            raise SleeperError(f"Network error fetching {url}: {exc.reason}") from exc
        finally:
            self._last_request_at = time.monotonic()

        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SleeperError(f"Response from {url} was not valid JSON: {exc}") from exc

        if parsed is None:
            raise SleeperError(
                f"{url} returned HTTP {status} with a JSON null body. "
                "Sleeper does this for IDs that do not exist -- check the ID you passed."
            )
        return parsed

    # ------------------------------------------------------------- users

    def get_user(self, username_or_id: str) -> dict:
        """GET /user/{username_or_id}. Sleeper accepts either form."""
        user = self._get(f"/user/{username_or_id}")
        if not isinstance(user, dict):
            raise SleeperError(f"/user/{username_or_id} returned {type(user).__name__}, expected object")
        if "user_id" not in user:
            raise SleeperError(
                f"/user/{username_or_id} response has no 'user_id' field. Keys present: {sorted(user)}"
            )
        return user

    def get_user_leagues(self, user_id: str, season: str, sport: str = "nfl") -> list[dict]:
        leagues = self._get(f"/user/{user_id}/leagues/{sport}/{season}")
        if not isinstance(leagues, list):
            raise SleeperError(
                f"/user/{user_id}/leagues/{sport}/{season} returned {type(leagues).__name__}, expected list"
            )
        return leagues

    # ----------------------------------------------------------- leagues

    def get_league(self, league_id: str) -> dict:
        league = self._get(f"/league/{league_id}")
        if not isinstance(league, dict):
            raise SleeperError(f"/league/{league_id} returned {type(league).__name__}, expected object")
        return league

    def get_league_drafts(self, league_id: str) -> list[dict]:
        drafts = self._get(f"/league/{league_id}/drafts")
        if not isinstance(drafts, list):
            raise SleeperError(f"/league/{league_id}/drafts returned {type(drafts).__name__}, expected list")
        return drafts

    # ------------------------------------------------------------ drafts

    def get_draft(self, draft_id: str) -> dict:
        draft = self._get(f"/draft/{draft_id}")
        if not isinstance(draft, dict):
            raise SleeperError(f"/draft/{draft_id} returned {type(draft).__name__}, expected object")
        return draft

    def get_draft_picks(self, draft_id: str) -> list[dict]:
        picks = self._get(f"/draft/{draft_id}/picks")
        if not isinstance(picks, list):
            raise SleeperError(f"/draft/{draft_id}/picks returned {type(picks).__name__}, expected list")
        return picks

    # ----------------------------------------------------------- players

    @property
    def players_cache_path(self) -> Path:
        return self.cache_dir / "players_nfl.json"

    @property
    def players_meta_path(self) -> Path:
        return self.cache_dir / "players_nfl.meta.json"

    def players_cache_age_hours(self) -> float | None:
        """Age of the cached dump in hours, or None if there is no usable cache."""
        if not self.players_cache_path.exists() or not self.players_meta_path.exists():
            return None
        try:
            meta = json.loads(self.players_meta_path.read_text())
            fetched_at = float(meta["fetched_at"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise SleeperError(
                f"Players cache metadata at {self.players_meta_path} is unreadable: {exc}. "
                "Delete the cache directory and re-run."
            ) from exc
        return (time.time() - fetched_at) / 3600.0

    def get_players(self, sport: str = "nfl", force_refresh: bool = False) -> dict[str, dict]:
        """Return the full player map, keyed by player_id (string).

        Served from disk unless the cache is missing, stale, or force_refresh is set.
        """
        age = self.players_cache_age_hours()
        use_cache = (
            not force_refresh
            and age is not None
            and age <= self.players_max_age_hours
        )

        if use_cache:
            try:
                players = json.loads(self.players_cache_path.read_text())
            except json.JSONDecodeError as exc:
                raise SleeperError(
                    f"Cached players dump at {self.players_cache_path} is corrupt: {exc}. "
                    "Delete it and re-run."
                ) from exc
        else:
            players = self._get(f"/players/{sport}")
            if not isinstance(players, dict):
                raise SleeperError(f"/players/{sport} returned {type(players).__name__}, expected object")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.players_cache_path.write_text(json.dumps(players))
            self.players_meta_path.write_text(
                json.dumps({"fetched_at": time.time(), "sport": sport, "count": len(players)}, indent=2)
            )

        if not players:
            raise SleeperError(f"/players/{sport} produced an empty player map")
        return players

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Read-only helpers for a personal, single-user fantasy football draft assistant built on the
Sleeper public API. Nothing is ever written back to Sleeper; nothing is scraped. Three console
commands turn a Sleeper league into offline research artifacts (a config YAML, chunked player
research batches, and a past-draft JSON fixture).

## Repo layout

```
src/sleeper_draft/   client.py discover.py batches.py past_draft.py yamlio.py __init__.py
tests/               test_client.py test_batches.py test_discover_and_past_draft.py conftest.py
```

The modules use **relative imports** (`from .client import ...`), so run them via the console
scripts or as the `sleeper_draft` package — not `python discover.py` directly. `pyproject.toml`
declares `packages = ["src/sleeper_draft"]`, `testpaths = ["tests"]`, and console scripts pointing
at `sleeper_draft.discover:cli`, etc.; the layout above is what makes all three resolve.

## Commands

```bash
uv sync                              # create .venv, install PyYAML + dev group (pytest, ruff), install package
uv run pytest                        # run the offline suite (no test touches the network)
uv run pytest tests/test_batches.py::<name>   # run a single test
uv run ruff check .                  # lint (E, F, I, UP, B; line-length 110, target py39)
```

Runtime deps are deliberately minimal: only PyYAML. Everything except YAML emitting is standard
library (`urllib`, `json`). The three console scripts:

```bash
uv run sleeper-discover --league-id <id> --out config.yaml
uv run sleeper-batches --byes byes.2026.json
uv run sleeper-past-draft --league-id <id> --back 1
```

No league ID, draft ID, username, or season is hardcoded — everything comes from CLI args or the
env vars `SLEEPER_USERNAME` / `SLEEPER_SEASON` / `SLEEPER_LEAGUE_ID` / `SLEEPER_CACHE_DIR`.

## Architecture

`client.py` is the single seam to Sleeper. `SleeperClient` wraps `GET`s against
`https://api.sleeper.app/v1` with three cross-cutting behaviors baked in:
- **Fail loud, never default.** Every method type-checks its response and raises `SleeperError`
  (or `SleeperHTTPError`) on anything unusable. A JSON `null` body — Sleeper's response for an ID
  that doesn't exist — is turned into an explicit error naming the bad ID.
- **Rate limiting.** `min_interval_s` (0.1s) floors the spacing between requests.
- **Players-dump caching.** The ~5MB `/players/nfl` dump is cached to `.cache/sleeper/`
  (`players_nfl.json` + `.meta.json`) and re-fetched only when older than `players_max_age_hours`
  (24h) or when `force_refresh` is passed.

The three CLI modules (`discover.py`, `batches.py`, `past_draft.py`) each follow the same shape:
`parse_args()` → `main()` returns an int exit code → `cli()` wraps `main()`, converts any
`SleeperError` into a stderr message + exit 1, and is the `[project.scripts]` entry point. This
is why `SleeperError` is the one exception type worth catching at the boundary.

- **`discover.py`** — league → draft/scoring/roster config. Uses a `require(obj, key, where)`
  helper that fetches a key or dies naming the missing field. A league ID alone is enough
  (league → drafts → draft needs no user lookup); without one it goes username + season → league
  list. Note `reversal_round` (third-round reversal) is undocumented by Sleeper, so the code
  reports exactly what it finds rather than assuming.
- **`batches.py`** — the research-list pipeline: `load_byes` → `select` (filter via `eligible`,
  then sort) → `to_entries` → `write_batches`. Ordering uses `search_rank` ascending (Sleeper's
  only ranking signal; **not ADP**), excluding the `9999999` sentinel, `null` ranks, inactive
  players, and free agents (`team is null`). Byes come from a required external JSON map because
  the player object has no bye field; a `0` placeholder or any missing team is a hard error that
  names every offender and writes nothing.
- **`past_draft.py`** — `walk_back` follows `previous_league_id` (bounded by `MAX_CHAIN_HOPS=30`)
  to a target season, then saves a full draft fixture (settings, `slot_to_roster_id`, every pick).
  Refuses to save unless pick count equals `teams * rounds` (override with `--allow-partial`).
  The fixture exists to verify snake/3RR pick-order math offline.

`yamlio.py` — one shared `dump_yaml` so `discover` and `batches` emit identical style
(`sort_keys=False` to preserve field order; PyYAML's resolver quotes traps like the team
abbreviation `NO`, which bare YAML 1.1 would read as boolean `false`).

## Testing model

Tests are fully offline. `conftest.py` provides:
- `build_players()` / `players_cache` — a synthetic dump shaped like the real one, deliberately
  including the awkward rows (null `fantasy_positions`, the `9999999` sentinel, free agents with
  `team=null`, defenses whose `player_id` is the team abbreviation and `full_name` is absent).
- `StubClient` — subclasses `SleeperClient` and replaces the HTTP methods with canned league /
  draft / pick data; the `stub_client` fixture monkeypatches `SleeperClient` in every CLI module.

When adding behavior, extend these fixtures rather than reaching for the network, and preserve the
edge-case rows — several tests exist specifically to pin behavior against them (e.g. the `NO`
boolean-quoting test).

## Sleeper data facts worth knowing

- `/players/nfl` has **no ADP, no projections, no bye week**. `search_rank` is the only ordering
  signal and is prominence, not ADP (noisy in the tail, with repeated values like `999`).
- Defenses use the team abbreviation as `player_id` (`"CAR"`) and have no `full_name`.
- `team: null` means free agent (can be true even for active players); `active` is independent of
  `status`.

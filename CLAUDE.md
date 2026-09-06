# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Read-only helpers for a personal, single-user fantasy football draft assistant built on the
Sleeper public API. Nothing is ever written back to Sleeper; nothing is scraped. Five console
commands turn a Sleeper league into offline artifacts: a config YAML, chunked player research
batches, a past-draft JSON fixture, the in-draft board, and the live draft state.

**The end use is live: during the draft, a TUI assistant reads `draft/` while `sleeper-live`
polls Sleeper.** `draft/PLAYBOOK.md` is the standing doctrine and is loaded first every session;
`draft/board.md` is the ranked board; `draft/state/NOW.md` is what is true right now. See "The
draft/ directory" below.

## Repo layout

```
src/sleeper_draft/   client.py discover.py batches.py past_draft.py board.py live.py
                     yamlio.py __init__.py
tests/               test_client.py test_batches.py test_discover_and_past_draft.py
                     test_board.py test_live.py conftest.py
research/rankings_2026.json    aggregate rankings keyed by NAME -- the board's input
research/scouting_notes.json  one-line scouting + flags + handcuff pairs, keyed by player_id
research/players/    one markdown note per player; filename ends in the Sleeper player_id
research/batches/    the input lists those notes were written from
draft/               PLAYBOOK.md + STRATEGY.md (hand-maintained) + board.md/board.json/
                     pick_order.json (generated) -- what the in-draft assistant reads
draft/state/         NOW.md + state.json, rewritten every poll (gitignored)
```

The modules use **relative imports** (`from .client import ...`), so run them via the console
scripts or as the `sleeper_draft` package — not `python discover.py` directly. `pyproject.toml`
declares `packages = ["src/sleeper_draft"]`, `testpaths = ["tests"]`, and console scripts pointing
at `sleeper_draft.discover:cli`, etc.; the layout above is what makes all five resolve.

## Commands

```bash
uv sync                              # create .venv, install PyYAML + dev group (pytest, ruff), install package
uv run pytest                        # run the offline suite (no test touches the network)
uv run pytest tests/test_batches.py::<name>   # run a single test
uv run ruff check .                  # lint (E, F, I, UP, B; line-length 110, target py39)
```

Runtime deps are deliberately minimal: only PyYAML. Everything except YAML emitting is standard
library (`urllib`, `json`). The five console scripts:

```bash
uv run sleeper-discover --league-id <id> --out config.yaml
uv run sleeper-batches --byes byes.2026.json
uv run sleeper-past-draft --league-id <id> --back 1
uv run sleeper-board
uv run sleeper-live --slot <n> --watch
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
- **`board.py`** — joins the name-keyed rankings to Sleeper `player_id`s and writes `draft/`.
  `research/rankings_2026.json` identifies players by name; the live draft feed identifies
  them by `player_id`, so nothing can be crossed off a board until that join exists. Matching is on normalised name (accents, punctuation and generational suffixes
  folded) + fantasy position, indexed on `fantasy_positions` rather than `position` so that
  players Sleeper files under a defensive position still match (Travis Hunter is
  `position: DB`, `fantasy_positions: [DB, WR]`). A row matching nothing or matching two
  players the tiebreakers can't separate is a hard error naming every offender, and nothing
  is written; `NAME_ALIASES` holds the source-vs-Sleeper spelling disagreements.
  `research/scouting_notes.json` is already keyed by `player_id` and merges straight on;
  an unknown id, an unknown flag, or a dangling `handcuff_for` is likewise a hard error.
  It also derives the pick-order table from the snake + reversal rule and **verifies it
  against the rankings file's own pick map** — 3RR is undocumented, so two derivations
  must agree.

- **`live.py`** — the only module that runs *during* the draft. Polls `/draft/<id>/picks` and
  rewrites `draft/state/`. It reads `draft/board.json` and `draft/pick_order.json` rather than
  the rankings, so a poll is one small request and every board field (tier, ADP, flags,
  scouting, research note path) is already attached to the `player_id` the pick feed returns.
  `summarize()` is pure — draft + picks + board in, whole state out — which is why the tests
  cover the pick-timing maths without any HTTP. Two deliberate asymmetries with the rest of the
  repo: an **off-board pick is not an error** (208 ranked, 156 picks, rivals draft whoever they
  like — those are recorded from Sleeper's pick metadata and listed separately), and a
  **missing slot is not an error either** — without `--slot`/`--username` the timing maths is
  skipped rather than guessed, since a wrong "picks until my next" is worse than none.

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
- `build_rankings()` / `rankings_file`, `notes_dir`, `scouting_file`, `league_config` — a
  name-keyed rankings document, research notes deliberately missing one ranked player, scouting
  notes covering the three real entry shapes (text-only, flags-only, handcuff pair), and a
  league config, for the board join. `tests/test_board.py` pins the generated 3RR pick table
  against the real 12x13 numbers.
- `draft_artifacts` / `make_picks()` — builds a real `board.json` + `pick_order.json` by running
  the actual generator, then synthesises picks in draft order. `tests/test_live.py` uses them so
  the two modules stay honest about the file shape they share; `make_picks` runs past the end of
  the board on purpose to exercise the off-board path.

When adding behavior, extend these fixtures rather than reaching for the network, and preserve the
edge-case rows — several tests exist specifically to pin behavior against them (e.g. the `NO`
boolean-quoting test).

## The `draft/` directory

This is the only directory the in-draft assistant should need. The join key is `player_id`
everywhere: live pick → `draft/board.md` row → `research/players/*-<player_id>.md`.

**Read the `.md` files, not the `.json` ones.** The JSON holds the same information 4–7x larger
(`board.json` is 4.6x `board.md`) because JSON repeats every field name on every row. The JSON
exists as a machine input: `board.json` and `pick_order.json` are what `live.py` parses, and
`state/state.json` is there for a future renderer or status line.

- **`PLAYBOOK.md`** — hand-maintained doctrine: hard constraints (no K, no DST — those slots
  do not exist), the 3RR pick table, the per-pick algorithm, the real positional cliffs,
  round-by-round plan, numeric thresholds, adaptation triggers, risk flags, and the data
  caveats. Edit it directly; it is not generated.
- **`STRATEGY.md`** — hand-maintained. The reasoning the playbook compresses: VORP and
  replacement math, structural approaches, roster shapes, QB/TE gap data, the RB dead zone,
  handcuffing, stacking, per-slot playbooks, rookies, market inefficiencies, and the source
  citations. This is the surviving record of the original research pack — nothing else holds
  those numbers or citations.
- **`board.md` / `board.json`** — 208 ranked players with `player_id`, tier, bye, the three
  source ranks, risk flags, Sleeper injury status, scouting line, flags, `handcuff_for`, and
  the path to each player's research note. Plus a positional index, the researched-but-unranked
  bin (late-round material), and a provenance section carrying the ranking sources and weights.
- **`pick_order.json`** — `picks_by_slot` and `slot_by_pick` for all 12 slots × 13 rounds.
- **`state/NOW.md`** and **`state/state.json`** — written by `sleeper-live` every poll, and
  gitignored because they turn over every few seconds during a draft. `NOW.md` is in reading
  order: whose pick, picks until mine comes back, my roster and open starting slots, who is at
  risk before my next pick, best available, tiers remaining, recent picks and runs.

Regenerate the three generated files with `uv run sleeper-board` after editing anything in
`research/`. `PLAYBOOK.md` and `STRATEGY.md` do not regenerate — update them by hand.

## Sleeper data facts worth knowing

- `/players/nfl` has **no ADP, no projections, no bye week**. `search_rank` is the only ordering
  signal and is prominence, not ADP (noisy in the tail, with repeated values like `999`).
- Defenses use the team abbreviation as `player_id` (`"CAR"`) and have no `full_name`.
- `team: null` means free agent (can be true even for active players); `active` is independent of
  `status`.

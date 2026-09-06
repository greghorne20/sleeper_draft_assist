# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Read-only helpers for a personal, single-user fantasy football draft assistant built on the
Sleeper public API. Nothing is ever written back to Sleeper; nothing is scraped. Six console
commands turn a Sleeper league into offline artifacts: a config YAML, chunked player research
batches, a past-draft JSON fixture, the in-draft board, the live draft state, and the keeper
eligibility ruling.

**Two modes of session, and they are not alike.** Building the tools is an engineering task
and this file describes it. **Advising during a live draft is not** — for that, read
`.claude/skills/draft-day/SKILL.md`, which frames the session, routes to the right files and
fixes the answer shape. `AGENTS.md` points non-Claude-Code agents at the same file.

**The end use is live: during the draft, a TUI assistant reads `draft/` while `sleeper-live`
polls Sleeper.** `draft/PLAYBOOK.md` is the standing doctrine and is loaded first every session;
`draft/board.md` is the ranked board; `draft/state/NOW.md` is what is true right now. See "The
draft/ directory" below.

## Repo layout

```
src/sleeper_draft/   client.py discover.py batches.py past_draft.py board.py live.py
                     serve.py live_view.html keepers.py yamlio.py __init__.py
src/sleeper_draft/warroom/  brief.py tools.py agent.py runner.py INSTRUCTIONS.md
tests/               test_client.py test_batches.py test_discover_and_past_draft.py
                     test_board.py test_live.py test_keepers.py test_serve.py
                     test_warroom.py conftest.py
research/rankings_2026.json    aggregate rankings keyed by NAME -- the board's input
research/scouting_notes.json  one-line scouting + flags + handcuff pairs, keyed by player_id
research/players/    one markdown note per player; filename ends in the Sleeper player_id
research/batches/    the input lists those notes were written from
draft/               PLAYBOOK.md + STRATEGY.md (hand-maintained) + board.md/board.json/
                     pick_order.json (generated) -- what the in-draft assistant reads
draft/state/         NOW.md + state.json + teams/, rewritten every poll (gitignored)
.claude/skills/      draft-day/SKILL.md -- the in-draft conversational framing
AGENTS.md            points non-Claude-Code agents at that skill
```

The modules use **relative imports** (`from .client import ...`), so run them via the console
scripts or as the `sleeper_draft` package — not `python discover.py` directly. `pyproject.toml`
declares `packages = ["src/sleeper_draft"]`, `testpaths = ["tests"]`, and console scripts pointing
at `sleeper_draft.discover:cli`, etc.; the layout above is what makes all six resolve.

## Commands

```bash
make check                           # lint + types + test -- the pre-commit gate
uv sync                              # create .venv, install PyYAML + dev group, install package
uv run pytest                        # run the offline suite (no test touches the network)
uv run mypy                          # type-check src/ (default strictness, clean)
uv run pytest tests/test_batches.py::<name>   # run a single test
uv run ruff check .                  # lint (E, F, I, UP, B; line-length 110, target py39)
```

Runtime deps are deliberately minimal: only PyYAML. Everything except YAML emitting is standard
library (`urllib`, `json`). The six console scripts:

```bash
uv run sleeper-discover --league-id <id> --out config.yaml
uv run sleeper-batches --byes byes.2026.json
uv run sleeper-past-draft --league-id <id> --back 1
uv run sleeper-board
uv run sleeper-live --slot <n> --watch
uv run sleeper-keepers --league-id <id>
uv run sleeper-warroom --watch          # optional: needs `uv sync --extra warroom`
```

A `Makefile` wraps all of the above (`make help`). It is convenience only -- every
target is a thin `uv run` wrapper -- and GNU make is not installed on a bare WSL box.
Two deliberate choices worth not re-litigating: **`ruff format` is not adopted** (it
would rewrite 16 of 18 files by exploding the compact argparse calls; `ruff check`
already handles import order), and **mypy runs at default strictness, not `--strict`**
(which reports 80 mostly-cosmetic findings on this dict-heavy code). `make fmt-check`
shows the formatter diff if that ever gets reconsidered.

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
  The state is computed in two halves and this is the load-bearing split: `summarize_league()`
  is everything true of the draft whatever seat you read it from, `slot_view()` is the part
  that depends on the seat and nothing else does. So **all twelve war rooms cost the same two
  HTTP requests as one** — the expensive half runs once per poll, and `summarize_all()` adds
  a small block per slot. `flatten()` merges one seat onto the shared state; `summarize()` and
  `team_state()` both end there, so the one-seat and twelve-seat paths cannot drift (a test
  pins every slot's projection against computing that slot alone). Urgency is per-seat, so the
  shared board carries no `leaving` flag — each war room carries `leaving_ids` and the flag is
  merged back on at render time, which is what keeps "urgency is a property of a player, not a
  second board" true without storing thirty rows twelve times.
  Both are pure — draft + picks + board in, whole state out — which is why the tests cover the
  pick-timing maths without any HTTP. **Keepers need no special case**: Sleeper feeds them as
  ordinary picks carrying `is_keeper`, at the pick number their round cost implies, so they
  leave the board through the same path as everything else and are only *labelled* differently.
  Two deliberate asymmetries with the rest of the
  repo: an **off-board pick is not an error** (208 ranked, 156 picks, rivals draft whoever they
  like — those are recorded from Sleeper's pick metadata and listed separately), and a
  **missing slot is not an error either** — without `--slot`/`--username` the timing maths is
  skipped rather than guessed, since a wrong "picks until my next" is worse than none. Team
  names are resolved once at startup, not per poll, and a league whose draft order is not drawn
  yet gets numbered rooms rather than an error. Before the order is drawn the names come from
  the roster map, which makes the *seating* provisional; `seating_provisional` carries that and
  `NOW.md` says so, but the page's war-room strip does not — it is a navigation control, and a
  caveat repeated on every render is noise rather than a warning.

- **`serve.py`** + **`live_view.html`** — the optional `sleeper-live --serve` page. A stdlib
  `ThreadingHTTPServer` on a daemon thread with exactly two literal routes (`/` → the packaged
  HTML, `/state.json` → the out-dir file, `no-store`); everything else 404s. It is deliberately
  **not** `SimpleHTTPRequestHandler` — never joining a request path to a directory makes
  traversal impossible by construction rather than by sanitising. `log_message` is a no-op so
  request logs do not bury the poll output. The poll loop and the server share nothing but the
  filesystem, and the only coordination between them is `os.replace` — every state file is
  written through a temp file and renamed, so a page refresh landing mid-write gets the previous
  poll rather than a truncated one. No fsync: the state is derived and rewritten every poll, so
  the next one rebuilds anything a power cut would cost. The page is vanilla JS with no build step and no libraries, re-renders in place to
  keep scroll position, and shows a banner when polls stop arriving — a silently frozen page
  during a draft is the dangerous failure. It is a dashboard, so state is encoded in form as
  well as number: position colour chips, a pick rail showing the 3RR cluster, tier bars that
  turn red at the two-left tier-break trigger, and a severity stripe on players leaving before
  your next pick. It shows **one seat at a time out of twelve**: `seatState()` in the page is
  the same projection `team_state()` does in Python, the war-room strip switches seats through
  the URL hash so a room can bookmark its own view, and the "Around the league" panel shows
  what every other team still has to fill. That cross-team view is **broadcast colour only and
  deliberately not an input to urgency** — `leaving` stays anchored to market ADP, because
  twelve rooms reading each other's needs and all reaching a round early is a feedback loop
  an external market number does not have. **There is one board, not two** — filtering it by ADP yields a strict subset
  in the same order, so a separate "at risk" table just printed the same players twice; urgency
  is a `leaving` flag on the row, with a filter to narrow to them. Google Fonts is the one external request, with a
  full fallback stack; the data path is localhost only. Theme tokens are defined in the bare
  `:root` and only *redefined* by the dark blocks — never define a colour solely inside a media
  query, or the un-stamped default renders one theme on the other's ground. Two tests parse the field names the page reads and assert
  they all exist in a generated state, so binding to a dropped field fails the suite.
- **`keepers.py`** — rules who may keep whom. Reuses `past_draft.walk_back` to reach last
  season, then reads that season's draft, final rosters and the full transaction log. Eligible
  = that team drafted him **and** he is on their final roster **and** no completed transaction
  dropped him from it **and** he was not last season's keeper; the cost is his draft round.
  The transaction check is the point: "on the final roster" and "never left" are different
  questions, and a player dropped in week 3 and re-added in week 9 passes the first while
  failing the second. They happened to agree for every 2025 roster, so any disagreement is
  reported rather than silently resolved. Trades need no special case — Sleeper puts the losing
  side in `drops`. `eligible_keepers()` is pure, so every rule has a test with no HTTP.
  **`keepers.md` is circulated to the league, so it carries only public data**: the optional
  board enrichment takes the market ADP and nothing else — never our rank, tier, scouting or
  flags. A test asserts none of those strings can reach the report.

- **`warroom/`** — the optional agent layer, and the only part of the repo that calls a model.
  `sleeper-warroom` watches the state `sleeper-live` writes and produces one agent-written brief
  per team — strategy, a proposed pick with reasoning, an alternative with what would flip it —
  into `draft/state/briefs.json`. **It is strictly additive and must stay that way:** it makes no
  Sleeper requests, holds no lock, shares nothing with the poller or the server but the
  filesystem, and is an optional extra (`agent-framework-core` + the Anthropic provider, 21
  packages; the umbrella `agent-framework` pulls 180). Kill it mid-draft and the page loses one
  panel — nothing else changes. The split inside mirrors the rest of the repo: `brief.py` is pure
  and holds every decision that does not need a model, `tools.py` is plain annotated callables
  with no framework import, and `agent.py` is the only file that imports Agent Framework.
  - **`validate_brief` is the correctness gate.** The worst failure here is recommending a player
    who is already gone, because it reads exactly like a good brief. Model output is checked
    against the board the way `board.py` checks a rankings row — available-set membership, id and
    name agreeing, no K or DST — then retried once with the problems fed back, then refused. An
    unvalidated brief never reaches the page.
  - **Briefs are written as each room lands, not once per cycle.** A first cycle regenerates all
    twelve and takes over a minute; `asyncio.gather` held every result until the slowest
    finished, so `/briefs.json` 404'd for 78 seconds after startup and a restart inside that
    window threw away every room that had already completed. `as_completed` plus a `persist`
    callback drops that to 3s for the endpoint and 18s for the first brief. The markdown is
    still written once per cycle — nothing polls it.
  - **`refresh_targets` decides who regenerates.** Not all twelve on every pick: a room refreshes
    when it is near its turn, just picked, had its proposal drafted, errored, or aged out.
    `--refresh all` forces every seat, at roughly four times the cost.
  - **Cross-team needs are colour, not an urgency input.** The prompt says so outright. Twelve
    rooms reading each other's needs and all reaching a round early is a feedback loop market ADP
    does not have, so `leaving` stays anchored to ADP.
  - **The hard rules are shared with the live advisor.** `INSTRUCTIONS.md` carries
    `.claude/skills/draft-day/SKILL.md`'s correctness rules verbatim and a test asserts both files
    still say them, so editing one alone fails the suite.
  - **The system prompt is prompt-cached, and that halves the bill.** `AnthropicChatOptions`
    takes `instructions` as either a string or Anthropic system blocks, and blocks are the
    documented way to attach `cache_control` — no wrapping of the raw client needed. Measured on
    one room, same state, back to back: `--no-cache` 29,210 input / 4,065 output ≈ $0.149;
    cached 11,445 input / 17,946 cache-read / 2,432 output ≈ $0.076. Total input volume is
    unchanged; 61% of it just moves from $3/MTok to $0.30. The TTL is 1h rather than Anthropic's
    default 5m because this league's pick timer is 300s, so a slow pick would expire the prefix
    exactly when the next brief needs it. `--no-cache` exists to re-measure.
  - **Most of the input is the agentic loop, not the prompt.** Every tool result re-sends the
    conversation, so a brief that reads three notes pays for the system prompt four times —
    which is exactly why caching a byte-identical prefix across twelve rooms pays off.
  - **Hot rooms get Sonnet, cold rooms get Haiku**, split on the same `hot_slots()` the refresh
    trigger uses so the two cannot drift. Output is over half a Sonnet brief's cost and caching
    cannot touch it, so the cheap model is the lever that remains. Warm, measured: Sonnet
    ~$0.0825, Haiku ~$0.0212. **The brief you act on is always Sonnet's** — a room within
    `--hot-within` picks of its turn regenerates every single pick, so by the time you are on
    the clock yours has been rewritten several times by the better model.
  - **Whole-draft cost, simulated across all 156 picks with the real trigger and pick order:**
    one model uncached ~$152, one model cached ~$84, cached + split ~$57 (574 hot + 444 cold).
    Sensitive to what the briefs name: a proposal that gets drafted regenerates that room, so
    briefs that keep recommending players who go immediately push it towards `--refresh all`
    (1,884 generations). Tuning `--hot-within 1 --cold-every 12` takes it to ~$34.

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
- `KEEPER_PICKS` / `KEEPER_ROSTERS` / `KEEPER_USERS` / `KEEPER_TRANSACTIONS` — a prior season
  carrying every keeper edge case on one roster: held all year, last season's keeper, dropped
  and re-added, dropped for good, a waiver pickup held to the end, a traded player, a failed
  claim, and a player absent from the players dump. `tests/test_keepers.py` pins one rule per
  test against them.
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
- **`state/briefs.json`**, **`state/briefs.md`** and **`state/teams/BRIEF-slot-<n>.md`** — written
  by `sleeper-warroom` when it is running, gitignored with the rest of `state/`. Deliberately not
  merged into `NOW.md`: the draft-day skill reads facts derived from Sleeper and reasons from the
  board, rather than reading another model's opinion and agreeing with it. Two independent
  advisors, not one echoing the other.
- **`keepers.md`** / **`keepers.json`** — per-team keeper eligibility with the round each
  would cost, plus who is blocked and why. Regenerate with `uv run sleeper-keepers`. Unlike
  everything else in `draft/`, this one leaves the machine — keep it to public data only.
- **`state/NOW.md`**, **`state/state.json`** and **`state/teams/`** — written by
  `sleeper-live` every poll, and gitignored because they turn over every few seconds during a
  draft. `NOW.md` is **my seat**, in reading order: whose pick, picks until mine comes back, my
  roster and open starting slots, who is at risk before my next pick, best available, tiers
  remaining, recent picks and runs. `state/teams/NOW-slot-<n>.md` is the same document for each
  of the other eleven seats. `state.json` is the whole league in one file: the shared board
  once, plus a `war_rooms` block per slot and `rosters_by_slot` for every team's picks —
  which is what the page's team switcher and "Around the league" panel read.
  **`NOW.md` keeping its old path and its old meaning is deliberate** — it is what lets the
  draft-day skill go on reading one file while the league view develops alongside it.

Regenerate the three generated files with `uv run sleeper-board` after editing anything in
`research/`. `PLAYBOOK.md` and `STRATEGY.md` do not regenerate — update them by hand.

## Deploying it

`Dockerfile` + `docker-entrypoint.sh` + `railway.toml` put the board and the war rooms on a
public URL for the couple of days around a draft. `uv run sleeper-board` is a **build step, not a
runtime one** — the entrypoint refuses to start if `draft/board.json` is missing rather than
serving an empty board.

- **One container, two processes.** They talk only through `draft/state/`, so splitting them
  would mean a shared volume for no benefit. The entrypoint supervises both and restarts either
  on exit, never faster than `RESTART_DELAY`.
- **No volume, no database.** Every file under `draft/state/` is derived and rewritten each poll,
  so a restart mid-draft rebuilds it in one cycle and briefs regenerate on their own. The image is
  stateless.
- **`numReplicas = 1` is a correctness constraint, not a cost setting.** Two replicas means two
  pollers against Sleeper's shared public API and two war rooms billing the same twelve briefs
  twice. Nothing coordinates between instances because nothing was meant to.
- **The war room is optional at runtime too.** No `ANTHROPIC_API_KEY`, and the entrypoint says so
  once and starts only the poller; the page renders without the brief panel.
- **No players dump ships or is fetched.** Nothing at runtime calls `/players/nfl` — the board
  already resolved every name to a `player_id` — so runtime inputs are ~1.2MB and there is no
  cold start.
- Env: `PORT` and `HOST` (both plumbed into `sleeper-live`), `SLEEPER_SLOT`, `SLEEPER_DRAFT_ID`,
  `ANTHROPIC_API_KEY`, `ANTHROPIC_CHAT_MODEL`, `WARROOM_REFRESH`. `.dockerignore` keeps `.env` out
  of the image — the key is a runtime secret, and an image layer is not somewhere anything can be
  deleted from.

**`serve.py` is a stdlib `ThreadingHTTPServer` and this puts it on the public internet.** That is
a deliberate, bounded call: three literal routes, no request path ever joined to a directory, no
body parsing, read-only, nothing to steal, up for days rather than months. What is genuinely
missing is any protection against resource exhaustion — a thread per connection, no timeouts, no
request size limits — so the platform edge is doing the real work. Do not leave it up after the
draft, and do not reach for this pattern for anything long-lived.

## Sleeper data facts worth knowing

- `/players/nfl` has **no ADP, no projections, no bye week**. `search_rank` is the only ordering
  signal and is prominence, not ADP (noisy in the tail, with repeated values like `999`).
- Defenses use the team abbreviation as `player_id` (`"CAR"`) and have no `full_name`.
- `team: null` means free agent (can be true even for active players); `active` is independent of
  `status`.

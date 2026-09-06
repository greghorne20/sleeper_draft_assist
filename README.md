# Sleeper draft tools

Read-only helpers for a personal, single-user fantasy draft assistant.
Nothing is written back to Sleeper. Nothing is scraped.

```
pyproject.toml            project metadata, deps, console scripts
uv.lock                   pinned resolution
byes.template.json        32-team bye map to fill in (see "Bye weeks")
src/sleeper_draft/
    client.py             API wrapper + disk cache for the 5MB players dump
    discover.py           league -> draft/scoring/roster config
    batches.py            ordered research list, chunked into YAML files
    past_draft.py         walk previous_league_id back, save a draft fixture
    board.py              rankings + research notes -> the in-draft board
    live.py               poll the live draft -> the current-state files
    keepers.py            last season's draft + rosters + trades -> keeper eligibility
    yamlio.py             shared YAML output settings
research/rankings_2026.json    aggregate rankings, keyed by name -- the board's input
research/scouting_notes.json  one-line scouting + flags + handcuff pairs, keyed by player_id
research/players/         one markdown note per player, filename ends in player_id
draft/                    what the in-draft assistant reads (see "The draft/ directory")
tests/                    offline tests; no test touches the network
```

## Setup

```bash
uv sync
```

That creates `.venv`, installs the one runtime dependency (PyYAML) and the dev
group (pytest, ruff), and installs this package so the three commands work.

```bash
uv run pytest        # 21 tests, all offline
uv run ruff check .
```

Runtime deps are deliberately thin: everything except YAML emitting is standard
library. PyYAML earns its place by handling a trap — bare YAML 1.1 reads the team
abbreviation `NO` as the boolean `false`, and PyYAML's resolver knows to quote it.
There's a test pinning that behaviour.

No league ID, draft ID, username or season is hardcoded anywhere. Everything comes
from CLI args or from `SLEEPER_USERNAME` / `SLEEPER_SEASON` / `SLEEPER_LEAGUE_ID` /
`SLEEPER_CACHE_DIR`.

---

## Usage

### 1. `sleeper-discover`

If you know your league ID, that's all you need — no user lookup happens:

```bash
uv run sleeper-discover --league-id LEAGUE_ID --out config.yaml
```

If you don't, start from your username and season to list your leagues:

```bash
uv run sleeper-discover --username YOUR_SLEEPER_NAME --season 2026
```

Prints a pasteable YAML block: `draft_id`, full draft settings, `rounds`, `teams`,
`reversal_round`, `slot_to_roster_id`, `draft_order`, `roster_positions`,
`scoring_settings`, and `previous_league_id`.

On `reversal_round`: it isn't in Sleeper's public docs, so the command reports what
it actually finds. If the key is absent it prints the full list of settings keys
present; if it's `0` or `null` it says Sleeper is reporting no reversal. Worth
checking before you trust it for 3RR.

### 2. `sleeper-batches`

```bash
cp byes.template.json byes.2026.json   # then fill in the weeks
uv run sleeper-batches --byes byes.2026.json
```

Writes `research/batches/batch_01.yaml` … with 220 QB/RB/WR/TE at 15 per file, plus a
final `batch_NN_k_def.yaml` with 12 kickers and 12 defenses. Each entry:

```yaml
players:
- player_id: '4046'
  name: Josh Allen
  pos: QB
  team: BUF
  bye: 12
  search_rank: 5
```

Flags: `--limit 220`, `--chunk-size 15`, `--kickers 12`, `--defenses 12`,
`--out-dir research/batches`, `--refresh-players`.

The first run fetches the 5MB dump and caches it under `.cache/sleeper/`. Later runs
reuse it until it's 24h old, and print the cache age either way.

### 3. `sleeper-past-draft`

```bash
uv run sleeper-past-draft --league-id LEAGUE_ID --back 1
uv run sleeper-past-draft --league-id LEAGUE_ID --season 2025
```

Walks `previous_league_id` back, then saves `fixtures/draft_<season>_<draft_id>.json`
containing the chain walked, league metadata, the full draft object (settings,
`reversal_round`, `slot_to_roster_id`) and every pick with its `pick_no`, `round`,
`draft_slot` and `roster_id`.

That's what you need for the 3RR check: generate your expected
`(round, slot) -> pick_no` table and diff it against the `pick_no` / `draft_slot`
pairs in the fixture. If your maths is right, every row matches.

It refuses to save a draft whose pick count isn't `teams * rounds`; pass
`--allow-partial` to override.

### 4. `sleeper-board`

```bash
uv run sleeper-board
uv run sleeper-board --rankings research/rankings_2026.json --out-dir draft
```

`research/rankings_2026.json` ranks players by **name**. Sleeper's live draft feed
identifies picks by **`player_id`**. Nothing can be crossed off a board keyed by
name, so this does that join once, offline, and writes `draft/board.json`,
`draft/board.md` and `draft/pick_order.json`.

`research/scouting_notes.json` is already keyed by `player_id` and is merged straight
onto the board rows: a one-line scouting note, flags (`risk`, `riser`, `faller`,
`value`, `handcuff`, `dead_zone`), and `handcuff_for` links pairing a backup to the
starter he backs up. An unknown `player_id`, an unknown flag, or a `handcuff_for`
pointing nowhere is a hard error -- a dropped note is research that silently
disappears.

Matching is on normalised name + fantasy position — accents, punctuation and
generational suffixes folded away, and indexed on `fantasy_positions` rather than
`position` so that players Sleeper files under a defensive position still match
(Travis Hunter is `position: DB`, `fantasy_positions: [DB, WR]`). A ranking row that
matches nothing, or matches two players the tiebreakers can't separate, is a hard
error naming every offender; nothing is written. `NAME_ALIASES` carries the handful
of spelling disagreements between the ranking sources and Sleeper.

`pick_order.json` is generated from the snake + reversal-round rule and then checked
against the rankings file's own pick map. A disagreement is an error — third-round
reversal is undocumented by Sleeper, so two independent derivations have to agree
before a draft gets planned around them.

---

### 5. `sleeper-live`

```bash
uv run sleeper-live --slot 12                 # one shot
uv run sleeper-live --slot 12 --watch         # poll until the draft completes
uv run sleeper-live --username greg --watch --interval 5
```

Polls `/draft/<id>/picks` and rewrites `draft/state/NOW.md` and
`draft/state/state.json`. Everything except the picks comes from what
`sleeper-board` already built -- `board.json` supplies rank, tier, ADP, flags and
scouting for a `player_id`, `pick_order.json` supplies the 3RR pick numbers -- so
a poll is one small request.

`NOW.md` is written in reading order: whose pick it is and how many picks until
yours comes back, your roster and which starting slots are still open, who is at
risk before your next pick (ADP within `--cushion` of the pick you have to
survive until), the best available board, how many players are left in each
positional tier, the recent picks and any positional run.

Your slot comes from `--slot`, or from `--username` resolved through the draft's
`draft_order`. Without one the pick-timing maths is skipped rather than guessed --
the at-risk list and "picks until my next" are simply absent.

The board ranks 208 players and 156 picks get made, so a rival drafting someone
unranked is normal, not an error: those picks are recorded from Sleeper's own
pick metadata and listed under "Off-board picks".

---

### 6. `sleeper-keepers`

```bash
uv run sleeper-keepers --league-id LEAGUE_ID
uv run sleeper-keepers --league-id <id> --season 2025
```

Rules who each team may keep, and what the pick costs. Walks `previous_league_id`
back to last season (reusing `walk_back` from `past_draft.py`), then reads that
season's draft, final rosters and the whole transaction log.

A player is eligible for a team iff **all four** hold: that team drafted him, he
is on their final roster, no completed transaction ever dropped him from that
roster, and he was not last season's keeper. The cost is the round he was
drafted in.

It reads the transaction log rather than trusting the final roster because they
answer different questions -- a player dropped in week 3 and re-added in week 9
is on the final roster but did not stay all year. Any player where the two
answers differ is listed at the foot of the report instead of being silently
admitted or dropped. Trades need no special case: Sleeper records the losing
side in `drops`, so a player traded away fails "never left" and a player traded
for fails "you drafted him".

When `draft/board.json` exists it also shows this year's **public market ADP**
next to each eligible player, which is what turns eligibility into a decision --
keeping George Pickens at his round-5 cost reads differently once you see the
market has him going around pick 19.

Only the ADP is taken off the board. This report is circulated to the league, so
our own rank, tier, scouting notes and flags never reach it; a test asserts that.
The board is optional, and a player with no ADP renders as a dash.

---

## The `draft/` directory

Everything the in-draft assistant reads, and nothing else:

| File | What it is | Written by |
|---|---|---|
| `PLAYBOOK.md` | Standing doctrine: constraints, pick order, the pick algorithm, cliffs, thresholds, risk flags. Load first, every session. | hand-maintained |
| `STRATEGY.md` | The reasoning behind the playbook: VORP math, structural approaches, QB/TE gap data, dead zone, handcuffing, stacking, slot playbooks, market inefficiencies, citations. | hand-maintained |
| `board.md` | 208 ranked players grouped by tier, with `player_id`, source ranks and risk flags, plus a positional index and the researched-but-unranked bin. | `sleeper-board` |
| `board.json` | The same board, machine-readable. | `sleeper-board` |
| `pick_order.json` | `picks_by_slot` and `slot_by_pick` for all 12 slots x 13 rounds. | `sleeper-board` |
| `state/NOW.md` | Live draft state: whose pick, your roster and gaps, at-risk players, best available, tiers left, recent picks and runs. | `sleeper-live` |
| `state/state.json` | The same, machine-readable. | `sleeper-live` |
| `keepers.md` | Per-team keeper eligibility and the round each would cost. The report to circulate. | `sleeper-keepers` |
| `keepers.json` | The same ruling, machine-readable. | `sleeper-keepers` |

The join key is `player_id` throughout: live pick -> board row -> `research/players/*-<player_id>.md`.

The `.md` files are for reading; the `.json` files are inputs for tooling. They hold the same
information 4-7x larger, because JSON repeats every field name on every row. `board.json` and
`pick_order.json` are what `sleeper-live` parses; `state/state.json` is there for a renderer or
status line, and carries only the fields a live view displays.

---

## What's actually in `/players/nfl`

I fetched the live dump and read the real objects rather than working from the docs
example. Per-player fields relevant to ordering and identity:

| Field | Type | Notes |
|---|---|---|
| `player_id` | string | Map key too. Defenses use the team abbreviation (`"CAR"`), not a number. |
| `search_rank` | int / null | Lower = more prominent. `9999999` is the "irrelevant" sentinel; some rows are `null`. |
| `position` | string / null | `null` on placeholder rows like "Duplicate Player". |
| `fantasy_positions` | list / null | Can be `null`; can hold multiple (`["DB","LB"]`). |
| `team` | string / null | `null` means free agent, including for genuinely active players. |
| `active` | bool | Independent of `status`; a player can be `active: true`, `status: "Inactive"`. |
| `full_name` | string / null | Absent or null on some rows, so names fall back to `first_name` + `last_name`. |
| `depth_chart_order` | int / null | Within-team ordering only, mostly null. |
| `years_exp`, `status`, `injury_status`, `number`, `age` | mixed | Context, not ranking. |

**There is no ADP field, no projection field, and no bye week field.**

### Ordering choice

`search_rank` is the only ranking signal in the dump, so `sleeper-batches` sorts by
it ascending. It is Sleeper's own prominence ordering, not ADP — it tracks roughly
with draft interest at the top of the pool and gets noisy in the tail, where you'll
see repeated values like `999`. Ties break by position, then name, then `player_id`,
so runs are stable across days.

Rows are excluded when `search_rank` is `null` or the `9999999` sentinel, when
`active` is not `true`, or when `team` is `null`. That last one matters: a real
free agent has `team: null` and would otherwise sort into the middle of your list
with no team and no bye.

If you want true ADP later, it isn't in this API — you'd pull it from last year's
draft picks (`sleeper-past-draft` gives you those) or an outside source.

### Bye weeks

The player object has no bye week, and none of the documented endpoints carry one.
Rather than guess at an undocumented schedule endpoint, `sleeper-batches` requires
`--byes` pointing at a JSON map:

```json
{"ARI": 8, "ATL": 5, "BAL": 7}
```

`byes.template.json` has all 32 abbreviations with `0` placeholders. `0` is rejected
on purpose, so a half-filled file fails loudly instead of producing wrong byes. If any
player's team is missing from the map, the command names every missing team and writes
nothing.

---

## Failure behaviour

Every command raises and exits 1 rather than defaulting:

- unknown username, league or draft ID (Sleeper returns JSON `null`; that's named as such)
- a missing `slot_to_roster_id`, `rounds`, `teams`, `roster_positions` or `scoring_settings`
- a player with no resolvable name (the `player_id` is printed)
- any team missing from the bye map (all of them are listed at once)
- fewer players surviving the filters than `--limit` requested
- a `previous_league_id` chain that ends before the season you asked for

## Rate limiting

The client spaces requests at least 100ms apart and caches the players dump for 24h.
A full session across all three commands is well under a dozen calls, against
Sleeper's 1000/min guidance.

## Testing note

The test suite runs against a synthetic player dump and a stubbed client, covering
the filters, the ordering, the YAML round-trip and every failure path above. Nothing
has been run against your real league — my sandbox can't reach `api.sleeper.app`, so
the first live run will be yours.

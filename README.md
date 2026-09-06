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
    yamlio.py             shared YAML output settings
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

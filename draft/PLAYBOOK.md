# In-draft playbook — 12-team half-PPR, 3RR (2026)

**Load this file first, every draft session.** It is the standing doctrine. The board and the
live state are separate files, listed below.

`draft/STRATEGY.md` holds the reasoning, numbers and citations behind every rule here.
This file is the operational subset — the part you actually run during the draft.

---

## 1. Where everything lives

| I need… | Read |
|---|---|
| **What is true right now — whose pick, my roster, who's at risk** | `draft/state/NOW.md` (rewritten every poll by `sleeper-live`) |
| League rules, scoring, roster slots | `config.yaml` (fetched from Sleeper — authoritative) |
| The ranked board, tiers, ADP, risk flags | `draft/board.md` — read this one |
| My pick numbers for a given draft slot | `draft/pick_order.json` — or the table in §3 |
| Everything known about one player | `research/players/*.md` — **the filename ends in the Sleeper `player_id`** |
| Why a rule says what it says — VORP math, gap data, citations | `draft/STRATEGY.md` |
| The market's own ranks and their provenance | `research/rankings_2026.json`, or the Provenance section of `draft/board.md` |
| Short scouting lines, flags, handcuff pairings | in `draft/board.md` already; source is `research/scouting_notes.json` |

**The join key is `player_id` everywhere.** Sleeper's live pick feed identifies players only by
`player_id`; `draft/board.md` carries it in the `id` column. Given a pick, go
`player_id` → board row → `research/players/*-<player_id>.md`.

Regenerate the board with `uv run sleeper-board` (offline; reads the cached players dump).

The `.json` files next to them — `board.json`, `pick_order.json`, `state/state.json` — are inputs
for tooling, not for reading. They carry the same information several times larger, because JSON
repeats every field name on every row. Read the `.md`.

---

## 2. Hard constraints — these are not preferences

- **12 teams · 13 rounds · snake with third-round reversal · 0.5 PPR.**
- **No kicker slot. No defense slot.** `enforce_position_limits` is on — those picks are not
  merely unwise, they are unavailable. Every one of the 13 picks is QB/RB/WR/TE.
- Starters: **QB / RB / RB / WR / WR / TE / FLEX**, plus **6 bench**. 156 total picks.
- FLEX is RB/WR/TE.
- Scoring shape that matters: **rushing yards 0.1/yd vs passing yards 0.04/yd** (10 yds per point
  vs 25) and **4-point passing TDs**. Designed runs are worth ~2.5x passing yards, so a rushing QB
  is worth real draft capital and a pocket QB is not.
- **Only 156 picks get made.** Anything past ~rank 160 on the board will go undrafted. Late picks
  are upside swings, never depth.

---

## 3. Pick order (third-round reversal)

Round 1 runs slot 1→12. Round 2 runs 12→1. **Round 3 runs 12→1 again** instead of flipping back.
Normal snake resumes in round 4. One flip, no second reversal.

| Slot | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 24 | 36 | 37 | 60 | 61 | 84 | 85 | 108 | 109 | 132 | 133 | 156 |
| 2 | 2 | 23 | 35 | 38 | 59 | 62 | 83 | 86 | 107 | 110 | 131 | 134 | 155 |
| 3 | 3 | 22 | 34 | 39 | 58 | 63 | 82 | 87 | 106 | 111 | 130 | 135 | 154 |
| 4 | 4 | 21 | 33 | 40 | 57 | 64 | 81 | 88 | 105 | 112 | 129 | 136 | 153 |
| 5 | 5 | 20 | 32 | 41 | 56 | 65 | 80 | 89 | 104 | 113 | 128 | 137 | 152 |
| 6 | 6 | 19 | 31 | 42 | 55 | 66 | 79 | 90 | 103 | 114 | 127 | 138 | 151 |
| 7 | 7 | 18 | 30 | 43 | 54 | 67 | 78 | 91 | 102 | 115 | 126 | 139 | 150 |
| 8 | 8 | 17 | 29 | 44 | 53 | 68 | 77 | 92 | 101 | 116 | 125 | 140 | 149 |
| 9 | 9 | 16 | 28 | 45 | 52 | 69 | 76 | 93 | 100 | 117 | 124 | 141 | 148 |
| 10 | 10 | 15 | 27 | 46 | 51 | 70 | 75 | 94 | 99 | 118 | 123 | 142 | 147 |
| 11 | 11 | 14 | 26 | 47 | 50 | 71 | 74 | 95 | 98 | 119 | 122 | 143 | 146 |
| 12 | 12 | 13 | 25 | 48 | 49 | 72 | 73 | 96 | 97 | 120 | 121 | 144 | 145 |

Formula for slot S, round R (12 teams): R1 → `S`; R2 → `25 − S`; R3 → `37 − S`;
R≥4 → even round `12(R−1) + S`, odd round `12R − S + 1`.

**Effect of 3RR:** slot 1 loses its back-to-back 2/3 turn (picks 1, 24, 36 — no pairing).
Slot 12 gains it (12, 13, 25 — three of the top 25). Slots 1–2 stay strong on raw player value,
slots 10–12 become genuinely good, and roughly **slots 8–9 are the weakest seats** — neither the
elite anchor nor the tight turn.

**Slot-specific opening plan:** slots 1–4 → anchor RB or elite WR, expect a 22-pick wait.
Slots 5–8 → flexible BPA. Slots 9–12 → plan to double-address at the 2/3 turn.

*Draft slot is not assigned yet. Fill it in here the moment it is known, and write out this
row's first six pick numbers.*

---

## 4. The pick algorithm — run this every pick

1. Update available players (drop everything already drafted).
2. Compute **picks until my next selection** = `next_pick_number − current_pick_number − 1`.
3. Mark every available player **at risk** = their market ADP ≤ `current_pick + picks_until_next + cushion`,
   where **cushion = 3–5**, wider (8+) for high-variance ADPs.
4. Decide, in this order:
   - **Tier-break rule.** If the current-best tier has **≤ (drafters picking before I return)**
     players left **and** the drop to the next tier is a real cliff → take the last man in that tier.
   - Else take the **highest-value player who will NOT survive** to my next pick.
   - Else (everyone I like survives) → **best player available**, or address a secondary need.
5. Tiebreak, in order: positional need → **rushing QB / pass-catching RB** → bye diversity →
   stack with a QB I own → lower injury risk.

**Reach only** to (a) secure the last man in a cliff tier, (b) take a specific rushing QB during a
QB run that will empty the tier, (c) land Bowers or McBride at the TE cliff. Cap the reach at
**one round (≤12 picks) above ADP.** Never reach for a QB early, a mid-tier TE, or a dead-zone RB.

---

## 5. The cliffs that are actually real

Overall value on this board declines **smoothly** — there is no single overall cliff to game.
The cliffs are positional. Draft against these, not against the overall list.

- **After the top 2 TEs (Bowers #24, McBride #29).** ~5.5 PPG drop to TE3. This is the one cliff
  worth a full-round reach.
- **After the top ~2 RB and top ~3 WR.**
- **Around RB22 and WR34** — the ends of the useful starter pools.
- **The QB board is flat.** Never reach. QB8–QB13 are separated by almost nothing and any of them
  starts all season.

**Positional-run reaction:** join a run only if the tier behind it has a real cliff (RB1s, top TEs).
If the position is deep and flat (QBs, mid-WRs) **let the run happen and take the value it pushes
down to me.** Never chase the 4th–8th player in a run at a flat position.

---

## 6. Round-by-round

- **R1–3 — best available RB/WR.** With 2RB/2WR/1FLEX I need four to five genuinely startable
  RB/WR and this is the only place to get them. **No QB.** A TE only if Bowers or McBride falls.
- **R4–7 — keep hammering RB/WR.** FLEX and the first bench pieces. If I missed the top 2 TEs,
  Loveland or Tyler Warren here is fair value; otherwise keep waiting.
- **R8–10 — take the one QB.** Also the TE if still empty; TE7–TE15 are interchangeable.
- **R11–13 — pure upside only.** Every pick is a live RB/WR swing since no K/DST. Priority:
  (a) the direct backup to my own starting RBs, (b) receivers with a path to volume if someone
  ahead of them misses time. **Never** a low-ceiling safe veteran.

**End-roster target:** 5–6 RB, 5–6 WR, 1 QB (2 only if the QB is high-variance), 1–2 TE.
**Minimum:** 5 RB, 5 WR, 1 QB, 1 TE.

---

## 7. Numeric thresholds

| Rule | Threshold |
|---|---|
| Wait on QB until | pick ~85+ (R8) — unless Josh Allen falls past ~pick 45 |
| Elite TE only if | Bowers/McBride available at my R3 or R4 pick (~ADP 40); else punt TE to ~pick 90+ |
| Tier-break reach cap | ≤ 12 picks (one round) above ADP, and only at a cliff |
| At-risk ADP cushion | +3 to +5; widen to 8+ for high-variance ADPs |
| Same-bye starters | ≤ 2 projected starters per bye week; hard-avoid 3+ |

**High-variance ADPs** (widen the cushion): Josh Jacobs (σ 19.5), Sam LaPorta (20.4),
MarShawn Lloyd (24.9), Jadarian Price (10.5), McBride/Bowers (8.6/8.4).

**Bye clusters to watch:** W6 (DET, CIN, MIN, KC), W11 (LAR, GB, ATL, ARI, NE, CLE),
W7 (BUF, WAS, LAC, JAX), W8 (SF, NO, NYG, HOU). Do **not** pass on value for a bye conflict —
with 7 starters and a waiver pool deepened by no K/DST, 2–3 same-bye starters is survivable and
fixable in-season. Break a tie on byes only when two players are otherwise equal.

---

## 8. FLEX: 3rd RB or 3rd WR?

- **3rd WR** if RB1/RB2 are stable workhorses — half-PPR WR depth is deeper and steadier.
- **3rd RB** if either starting RB is fragile or in a committee (Henry age, McCaffrey, Jeanty
  ankle), or if a clear bell-cow falls to value. RB scarcity plus injury attrition makes a
  startable third RB league-winning.
- A pass-catching RB (Achane, Swift, Etienne) is the ideal half-PPR FLEX — floor and ceiling.

---

## 9. Adaptation triggers

| If I observe | Switch to |
|---|---|
| RB tiers 1–2 gone by my R2 pick | **Zero/Modified-RB** — hammer WR tiers 2–3 + an elite TE, collect upside RBs from R5 |
| Bowers or McBride falls to R4 | **Take it** — pivot to the elite-TE build (5 RB / 5 WR / 2 TE) |
| A QB run starts before R8 and tier-2 QBs are emptying | Take **one** rushing QB I like, then resume skill BPA |
| Elite WRs sliding past ADP (soft WR market) | **Load WR** — take the value, mine RB value in the dead zone |
| I hold a Gibbs/Bijan-type anchor and it's R3–4 | Lock a WR1, then attack WR depth; RB2 can wait to the dead zone if a volume back is there |
| My RB1 or RB2 is fragile | Prioritise a 3rd RB **and** that player's handcuff earlier than planned |
| Two elite options tie | rushing QB > pass-catching RB > stack > lower injury risk > bye diversity |

---

## 10. Risk flags (as of 2026-09-05 — re-verify at draft time)

| Player | Flag |
|---|---|
| Josh Jacobs | **OUT INDEFINITELY** — Commissioner's Exempt List. Near-zero value in 13 rounds; board has him 121, market 76 |
| Ashton Jeanty | Ankle — Week 1 unconfirmed, committee risk |
| Puka Nacua | Under active NFL conduct review — in-season suspension possible |
| Sam LaPorta | Injury question into Week 1 |
| Jonathon Brooks | Injury return uncertainty |
| Oronde Gadsden II | Buried on the depth chart — **avoid** |
| Deebo Samuel Sr. | Sources disagree on his team — verify before drafting |

**Unsettled as of Sep 5, re-verify:** Jeanty (ankle), Egbuka (toe), Chase (knee), Higgins (heel),
Love (ankle), Burden (groin). These are the picks most likely to have moved.

### Where this board deliberately disagrees with the market

| Player | Board | Market (FFC) | Why |
|---|---|---|---|
| MarShawn Lloyd | 75 | 116 | Lead Green Bay back now that Jacobs is on the exempt list |
| Josh Jacobs | 121 | 76 | Cannot practice or play, no timetable |
| Makai Lemon | 97 | 126 | Expert and best-ball sources are well ahead of redraft ADP post-A.J. Brown trade |
| Mike Washington Jr. | 132 | 160 | Standalone role even when Jeanty is healthy |
| Matthew Stafford | 106 | 77 | QB12 in a one-QB league is replaceable; the market still pays up |
| Alec Pierce | 83 | 61 | Redraft ADP is ahead of both other sources |

---

## 11. Do not draft

- **Any kicker.** **Any defense.** No roster slot exists.
- Oronde Gadsden II.
- Any low-ceiling "safe" veteran in R11–13.

## First waiver claims

- Kaleb Johnson (GB) — first claim if he takes early-down work
- Chris Brooks (GB)
- Mike Washington Jr., if Jeanty misses Week 1

---

## 12. Caveats about this data

- **`search_rank` in the Sleeper dump is not ADP.** It is prominence, noisy in the tail, with
  repeated values. It ordered the research batches; it must not order draft decisions. Use the
  board's `rank`/`tier` and the FFC/UD/RW source ranks.
- **The board is a 2026-09-05 snapshot.** ADP drifts daily and moves sharply on injury news.
- **VORP figures in the research pack come primarily from one projection source.** Trust the
  ordering, not the absolute point values.
- **`/players/nfl` has no ADP, no projections, and no bye week.** Byes on the board come from the
  rankings file, cross-checked against `byes.2026.json`.
- **17 ranked players (all rank 158+) have no research note**, and 29 researched players fall
  outside the ranked 208. Both lists are at the bottom of `draft/board.md`.
- Win-rate and draft-slot studies cited in the research pack are directional evidence from
  single-season samples, not guarantees.

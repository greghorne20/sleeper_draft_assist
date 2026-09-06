# Draft board — 12-team half-PPR - Season 22 (2026)

12 teams · 13 rounds · snake w/ round-3 reversal · starters QB/RB/RB/WR/WR/TE/FLEX · **no K, no DST**

208 ranked players. Source: 2026 Aggregate Fantasy Draft Rankings - 12-team half-PPR, Season 22 (generated 2026-09-05). Scoring: 0.5 PPR, 4pt pass TD, 25 yds/passing pt, -2 INT, -2 fumble lost.

Regenerate with `uv run sleeper-board`. **This file is the one to read** — `draft/board.json` holds the same board plus join fields, and exists as the input `sleeper-live` and other tooling parse. It is ~4.6x this file.

**Columns** — `#` overall rank · `Pos` positional rank · `Bye` bye week · `id` Sleeper player_id (the join key to live picks) · `FFC`/`UD`/`RW` source ranks (FantasyFootballCalculator ADP / Underdog ADP / Rotoworld) · `Δ` this board minus the market, positive means we like them more than ADP does.

**Flags** — `risk` injury or situation risk · `riser` trending up · `faller` trending down · `value` under-drafted relative to projection · `handcuff` contingent value behind a starter · `dead_zone` sits in the 2026 RB dead zone. Strategy behind all of it: `draft/STRATEGY.md`.

Full research on a player: `research/players/` — the filename ends in their `id`.

## Tier 1 — ranks 1-19 (19 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 1 | RB1 | Jahmyr Gibbs | DET | 6 | 9221 | 1.5 | 1.1 | 1 | 0 | Consensus 1.01; Montgomery gone → bigger role; proj ~300 |
| 2 | RB2 | Bijan Robinson | ATL | 11 | 9509 | 2.2 | 2.0 | 2 | 0 | 1.01-caliber |
| 3 | WR1 | Ja'Marr Chase | CIN | 6 | 7564 | 3.9 | 3.1 | 3 | 1 | Sleeper: Questionable · `risk` · minor knee (practice, Aug 25) — expected fine |
| 4 | WR2 | Jaxon Smith-Njigba | SEA | 11 | 9488 | 5.6 | 5.5 | 5 | 1 | Led NFL with 33.9% target share in '25 — "the biggest mark since DeAndre Hopkins' 34.7% back in 2017" (Draft Sharks); 163 targets, WR2 in PPR |
| 5 | RB3 | Christian McCaffrey | SF | 8 | 4034 | 6.2 | 6.0 | 6 | 2 | Sleeper: Questionable · `risk` · age/injury history; handcuff Jordan James |
| 6 | WR3 | Puka Nacua | LAR | 11 | 9493 | 2.9 | 4.2 | 4 | -3 | **⚠ Under active NFL conduct review - in-season suspension possible** · Sleeper: Questionable · `risk` · All-time WR1 PPG; monitor recovery · Led the NFL with 129 catches and 1,715 yards in 2025. Not suspended and expected to play Week 1, but remains under active NFL Personal Conduct Policy review - an in-season suspension is possible at any point. |
| 7 | RB4 | Jonathan Taylor | IND | 13 | 6813 | 5.8 | 7.8 | 8 | -1 | Workhorse |
| 8 | WR4 | Amon-Ra St. Brown | DET | 6 | 7547 | 7.6 | 7.1 | 7 | 0 | 3 straight WR4 finishes; safe |
| 9 | RB5 | James Cook | BUF | 7 | 8138 | 9.3 | 10.1 | 11 | 0 | TD-dependent |
| 10 | WR5 | CeeDee Lamb | DAL | 14 | 6786 | 12.0 | 9.8 | 10 | 2 |  |
| 11 | WR6 | Justin Jefferson | MIN | 6 | 6794 | 13.1 | 10.8 | 9 | 2 | Kyler QB upgrade could unlock ceiling |
| 12 | RB6 | De'Von Achane | MIA | 6 | 9226 | 10.9 | 16.9 | 13 | -1 | `value` · Receiving upside (half-PPR ) |
| 13 | RB7 | Saquon Barkley | PHI | 10 | 4866 | 16.5 | 13.0 | 12 | 3 | New OC Mannion; RB14 in '25 down yr |
| 14 | RB8 | Derrick Henry | BAL | 13 | 3198 | 10.1 | 16.5 | 17 | -4 | `risk` · late-career; still elite |
| 15 | RB9 | Chase Brown | CIN | 6 | 9224 | 13.7 | 14.3 | 19 | -1 | Volume |
| 16 | WR7 | Drake London | ATL | 11 | 8112 | 13.8 | 22.3 | 14 | -1 |  |
| 17 | RB10 | Kenneth Walker III | KC | 5 | 8151 | 20.5 | 14.2 | 18 | 3 | New team KC; TD upside |
| 18 | WR8 | A.J. Brown | NE | 11 | 5859 | 17.1 | 18.4 | 20 | -1 | New team NE; reunites w/ Vrabel |
| 19 | WR9 | Nico Collins | HOU | 8 | 7569 | 21.1 | 21.8 | 15 | 2 | `riser` · Higgins ACL → more targets |

## Tier 2 — ranks 20-38 (19 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 20 | WR10 | Rashee Rice | KC | 5 | 10229 | 17.3 | 27.3 | 22 | -2 |  |
| 21 | RB11 | Omarion Hampton | LAC | 7 | 12507 | 22.2 | 15.6 | 24 | 1 |  |
| 22 | WR11 | George Pickens | DAL | 14 | 8137 | 19.3 | 23.6 | 23 | -3 | New team DAL |
| 23 | WR12 | Malik Nabers | NYG | 8 | 11632 | 26.0 | 22.1 | 21 | 3 | Sleeper: Questionable · `riser` · on track Wk1; Dart QB |
| 24 | TE1 | Brock Bowers | LV | 13 | 11604 | 40.3 | 20.1 | 16 | 18 | _draft at value R3–4_ · Proj TE1 ~203; new HC Kubiak/QB Cousins; healthy = MVP candidate |
| 25 | WR13 | Chris Olave | NO | 8 | 8144 | 23.2 | 27.3 | 26 | 0 |  |
| 26 | RB12 | Ashton Jeanty | LV | 13 | 12527 | 23.1 | 16.3 | 29 | -3 | **⚠ Ankle - Week 1 unconfirmed, committee risk** · Sleeper: Questionable · `risk` · low ankle sprain (Aug 23); trending Wk1 but uncertain; Mike Washington Jr. eating early role · Low ankle sprain Aug 23, has not practiced since. Raiders 'optimistic' for Sep 13 but unconfirmed, and Washington has carved out a role regardless. |
| 27 | RB13 | Kyren Williams | LAR | 11 | 8150 | 27.6 | 30.8 | 28 | 0 | `dead_zone` · Corum lurks |
| 28 | RB14 | Jeremiyah Love | ARI | 14 | 13287 | 28.7 | 28.8 | 31 | 0 | Sleeper: Questionable · `dead_zone` `risk` · rookie, high-ankle sprain reported; 3rd overall pick talent |
| 29 | TE2 | Trey McBride | ARI | 14 | 8130 | 39.4 | 29.4 | 25 | 12 | 252.9 half-PPR pts in '25 (~90 more than next TE); NFL-record 126 catches; TD regression risk |
| 30 | WR14 | Zay Flowers | BAL | 13 | 9997 | 23.1 | 31.2 | 37 | -6 | Sleeper: Questionable |
| 31 | RB15 | Javonte Williams | DAL | 14 | 7588 | 30.2 | 33.5 | 32 | -1 | `dead_zone` |
| 32 | QB1 | Josh Allen | BUF | 7 | 4984 | 30.6 | 37.1 | 30 | -1 | Only QB >24 proj PPG; QB1/QB2 five straight yrs; DJ Moore added. Pay up ONLY if he slides to R4–5. |
| 33 | WR15 | DeVonta Smith | PHI | 10 | 7525 | 30.8 | 27.7 | 39 | -1 | `riser` · absorbs A.J. Brown targets |
| 34 | RB16 | Breece Hall | NYJ | 13 | 8155 | 31.6 | 30.9 | 36 | 0 | Sleeper: Questionable · `dead_zone` |
| 35 | RB17 | Travis Etienne Jr. | NO | 8 | 7543 | 37.4 | 40.3 | 27 | 2 | `dead_zone` · New team |
| 36 | WR16 | Tetairoa McMillan | CAR | 5 | 12526 | 31.4 | 40.6 | 33 | -3 | Yr-2 OROY; possible slot boost = WR1 ceiling |
| 37 | WR17 | Tee Higgins | CIN | 6 | 6801 | 34.4 | 34.9 | 35 | -2 | Sleeper: Questionable · `risk` · heel contusion (minor, Wk1 OK); injury-prone history |
| 38 | WR18 | Garrett Wilson | NYJ | 13 | 8146 | 29.5 | 39.0 | 46 | -9 |  |

## Tier 3 — ranks 39-57 (19 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 39 | WR19 | Ladd McConkey | LAC | 7 | 11635 | 40.6 | 33.6 | 38 | 4 |  |
| 40 | WR20 | Emeka Egbuka | TB | 10 | 12514 | 35.3 | 35.5 | 48 | -4 | Sleeper: Questionable · `risk` · sprained toe, questionable Wk1; Evans gone = target upside |
| 41 | RB18 | Cam Skattebo | NYG | 8 | 12481 | 38.3 | 46.2 | 41 | -1 | `dead_zone` `riser` · recovered, sharing w/ Tracy |
| 42 | WR21 | Jaylen Waddle | DEN | 10 | 7526 | 44.7 | 37.1 | 42 | 3 | New team DEN |
| 43 | RB19 | D'Andre Swift | CHI | 10 | 6790 | 41.0 | 44.6 | 44 | 1 | Sleeper: Questionable · `dead_zone` · _dead zone R5–7_ · Receiving |
| 44 | WR22 | Davante Adams | LAR | 11 | 2133 | 37.6 | 51.9 | 52 | -6 | New team LAR |
| 45 | RB20 | Bucky Irving | TB | 10 | 11584 | 47.2 | 52.9 | 40 | 2 | `dead_zone` `riser` · full-speed post-shoulder surgery |
| 46 | WR23 | Jameson Williams | DET | 6 | 8148 | 37.8 | 50.3 | 55 | -7 |  |
| 47 | TE3 | Colston Loveland | CHI | 10 | 12517 | 58.2 | 43.6 | 34 | 12 | `riser` · _young studs R5–7_ · elite late-'25 stretch; Ben Johnson offense |
| 48 | WR24 | Terry McLaurin | WAS | 7 | 5927 | 45.0 | 49.0 | 54 | -2 |  |
| 49 | RB21 | Quinshon Judkins | CLE | 11 | 12512 | 49.4 | 54.8 | 47 | 1 | `dead_zone` |
| 50 | RB22 | David Montgomery | HOU | 8 | 5892 | 55.1 | 47.5 | 43 | 7 | `dead_zone` `value` · New team; ~12.3 proj PPG |
| 51 | RB23 | Bhayshul Tuten | JAX | 7 | 12490 | 51.9 | 49.5 | 50 | 1 | Sleeper: Questionable · `dead_zone` · Upside |
| 52 | WR25 | Luther Burden III | CHI | 10 | 12519 | 53.6 | 44.5 | 57 | 1 | Sleeper: Questionable · `risk` · _upside R6–8_ · groin, ~month out |
| 53 | WR26 | Mike Evans | SF | 8 | 2216 | 55.0 | 52.6 | 49 | 3 | Sleeper: Questionable · New team SF |
| 54 | QB2 | Lamar Jackson | BAL | 13 | 4881 | 55.8 | 56.9 | 45 | 4 | `riser` · Bounce-back after injury-marred '25; rushing floor |
| 55 | WR27 | DJ Moore | BUF | 7 | 4983 | 47.6 | 52.8 | 62 | -7 | New team BUF |
| 56 | WR28 | Rome Odunze | CHI | 10 | 11620 | 48.8 | 58.0 | 61 | -7 | Sleeper: Questionable · Yr-2 upside |
| 57 | WR29 | Christian Watson | GB | 11 | 8167 | 53.8 | 57.2 | 60 | -3 | `risk` · ACL recovery |

## Tier 4 — ranks 58-73 (16 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 58 | QB3 | Drake Maye | NE | 11 | 11564 | 51.8 | 67.2 | 66 | -7 | Led NFL passing efficiency '25; rushing upside |
| 59 | RB24 | TreVeyon Henderson | NE | 11 | 12529 | 64.2 | 60.5 | 51 | 7 | Sleeper: Questionable · `dead_zone` · Could seize job |
| 60 | RB25 | Jadarian Price | SEA | 11 | 13286 | 67.1 | 59.4 | 53 | 9 | Rookie, wide-open room |
| 61 | WR30 | Parker Washington | JAX | 7 | 9487 | 63.1 | 56.1 | 64 | 3 |  |
| 62 | RB26 | Jaylen Warren | PIT | 9 | 8228 | 63.1 | 70.1 | 65 | 1 | `dead_zone` · Dowdle competition |
| 63 | TE4 | Tyler Warren | IND | 13 | 12518 | 69.4 | 63.3 | 56 | 8 | Sleeper: Questionable · Rookie stud |
| 64 | RB27 | Rhamondre Stevenson | NE | 11 | 7611 | 62.9 | 68.0 | 76 | -2 | `dead_zone` `riser` · momentum |
| 65 | WR31 | Carnell Tate | TEN | 9 | 13279 | 75.8 | 62.7 | 59 | 13 | Sleeper: Questionable |
| 66 | WR32 | Marvin Harrison Jr. | ARI | 14 | 11628 | 65.3 | 66.2 | 74 | 1 | Bounce-back |
| 67 | WR33 | DK Metcalf | PIT | 9 | 5846 | 63.2 | 74.4 | 72 | -2 | Sleeper: Questionable · New team PIT |
| 68 | WR34 | Brian Thomas Jr. | JAX | 7 | 11631 | 71.1 | 65.1 | 69 | 4 | `value` · talent > ADP |
| 69 | QB4 | Joe Burrow | CIN | 6 | 6770 | 54.3 | 68.7 | 63 | -14 | Full health = Chase/Higgins ceiling |
| 70 | QB5 | Jayden Daniels | WAS | 7 | 11566 | 73.9 | 69.9 | 58 | 4 | `value` · Elite rush profile; Diggs+McLaurin |
| 71 | RB28 | Tony Pollard | TEN | 9 | 5967 | 68.6 | 77.8 | 73 | -1 | _upside/contingent R7–10_ |
| 72 | RB29 | Rico Dowdle | PIT | 9 | 7021 | 74.5 | 83.6 | 71 | 3 | `handcuff` · ✂️ handcuff for Jaylen Warren · standalone value |
| 73 | WR35 | Courtland Sutton | DEN | 10 | 5045 | 61.4 | 82.9 | 92 | -13 | `faller` · Waddle lowers ceiling |

## Tier 5 — ranks 74-91 (18 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 74 | WR36 | Michael Wilson | ARI | 14 | 10232 | 72.9 | 90.9 | 82 | -1 |  |
| 75 | RB30 | MarShawn Lloyd | GB | 11 | 11581 | 114.5 | 143.5 | 67 | 41 | `handcuff` · Lead Green Bay back with Jacobs on the exempt list. Only 7 career touches and an injury history, but the touches are there now. Biggest post-cutdown riser. |
| 76 | RB31 | J.K. Dobbins | DEN | 10 | 6806 | 79.5 | 96.2 | 78 | 5 | `risk` · injury history |
| 77 | TE5 | Harold Fannin Jr. | CLE | 11 | 12506 | 76.0 | 104.9 | 70 | 2 | Most productive college TE ever |
| 78 | QB6 | Jalen Hurts | PHI | 10 | 6904 | 81.5 | 72.4 | 80 | 4 |  |
| 79 | QB7 | Dak Prescott | DAL | 14 | 3294 | 65.8 | 80.5 | 84 | -11 | _TARGET ZONE R8–11_ · Lamb+Pickens |
| 80 | WR37 | Chris Godwin Jr. | TB | 10 | 4037 | 78.0 | 84.3 | 93 | 0 | `risk` · injury recovery |
| 81 | WR38 | Jayden Reed | GB | 11 | 10222 | 85.5 | 78.1 | 91 | 4 | _darts R8–11_ |
| 82 | WR39 | Jordan Addison | MIN | 6 | 9756 | 90.4 | 89.0 | 77 | 9 |  |
| 83 | WR40 | Alec Pierce | IND | 13 | 8142 | 61.7 | 94.4 | 115 | -22 |  |
| 84 | RB32 | Jonathon Brooks | CAR | 5 | 11583 | 90.5 | 76.5 | 75 | 8 | **⚠ Injury return uncertainty** · Sleeper: Questionable · Still an injury-return question mark; sources are split. |
| 85 | TE6 | Tucker Kraft | GB | 11 | 9484 | 93.5 | 77.2 | 81 | 9 | Sleeper: Questionable · `value` · Elite YAC |
| 86 | WR41 | Josh Downs | IND | 13 | 9500 | 94.5 | 83.3 | 90 | 9 | Sleeper: Questionable |
| 87 | RB33 | Chuba Hubbard | CAR | 5 | 7594 | 87.9 | 98.2 | 94 | 1 | Sleeper: Questionable |
| 88 | WR42 | Quentin Johnston | LAC | 7 | 9754 | 85.0 | 75.0 | 114 | -4 |  |
| 89 | QB8 | Caleb Williams | CHI | 10 | 11560 | 88.6 | 73.5 | 89 | 0 | Yr-2 Ben Johnson leap; rushing |
| 90 | RB34 | Blake Corum | LAR | 11 | 11586 | 117.7 | 87.3 | 68 | 28 | `handcuff` `value` · ✂️ handcuff for Kyren Williams · best standalone handcuff |
| 91 | RB35 | RJ Harvey | DEN | 10 | 12489 | 108.0 | 87.7 | 79 | 19 | Zero-RB target |

## Tier 6 — ranks 92-114 (23 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 92 | WR43 | Jakobi Meyers | JAX | 7 | 5947 | 87.8 | 120.4 | 99 | -5 | Sleeper: Questionable |
| 93 | WR44 | Stefon Diggs | WAS | 7 | 2449 | 96.9 | 94.0 | 105 | 5 | `riser` `value` · signed WAS Aug 7; WR49 ADP value |
| 94 | RB36 | Kyle Monangai | CHI | 10 | 12534 | 107.2 | 107.0 | 87 | 15 | Sleeper: Questionable · `risk` · banged up |
| 95 | WR45 | Wan'Dale Robinson | TEN | 9 | 8126 | 94.7 | 113.9 | 100 | 1 | Sleeper: Questionable |
| 96 | WR46 | Michael Pittman Jr. | PIT | 9 | 6819 | 81.7 | 101.5 | 125 | -13 | Sleeper: Questionable |
| 97 | WR47 | Makai Lemon | PHI | 10 | 13294 | 129.3 | 80.8 | 83 | 29 |  |
| 98 | WR48 | Xavier Worthy | KC | 5 | 11624 | 97.8 | 107.0 | 104 | 1 |  |
| 99 | RB37 | Kenny Gainwell | TB | 10 | 7567 | 100.4 | 109.1 | 102 | 3 | _handcuffs/darts R10+_ |
| 100 | QB9 | Justin Herbert | LAC | 7 | 6797 | 104.3 | 84.2 | 85 | 7 | `value` · value |
| 101 | WR49 | Romeo Doubs | NE | 11 | 8121 | 99.0 | 116.9 | 103 | -1 |  |
| 102 | RB38 | Jacory Croskey-Merritt | WAS | 7 | 12533 | 101.2 | 100.2 | 112 | 1 | Sleeper: Questionable · Upside |
| 103 | QB10 | Patrick Mahomes | KC | 5 | 4046 | 103.9 | 97.7 | 86 | 2 | Sleeper: Questionable · `faller` · rush volume expected down; ceiling capped |
| 104 | QB11 | Brock Purdy | SF | 8 | 8183 | 86.3 | 103.0 | 108 | -18 | `value` · major value (QB1 per-game late '25 per CBS) |
| 105 | TE7 | Kyle Pitts Sr. | ATL | 11 | 7553 | 94.9 | 102.3 | 95 | -8 | `riser` · erupted 2nd-half '25 |
| 106 | QB12 | Matthew Stafford | LAR | 11 | 421 | 75.5 | 111.0 | 116 | -29 |  |
| 107 | RB39 | Aaron Jones Sr. | MIN | 6 | 4199 | 104.2 | 127.9 | 97 | -1 |  |
| 108 | WR50 | Matthew Golden | GB | 11 | 12501 | 99.2 | 100.1 | 121 | -7 | Rookie |
| 109 | RB40 | Jordan Mason | MIN | 6 | 8408 | 110.4 | 97.2 | 110 | 4 | `handcuff` |
| 110 | TE8 | George Kittle | SF | 8 | 4217 | 89.8 | 112.1 | 113 | -20 | Sleeper: Questionable · `risk` · _streaming-plus R8–11_ · Achilles recovery |
| 111 | WR51 | KC Concepcion | CLE | 11 | 13298 | 113.9 | 111.3 | 109 | 4 |  |
| 112 | RB41 | Rachaad White | WAS | 7 | 8136 | 127.9 | 117.7 | 96 | 12 | Sleeper: Questionable |
| 113 | TE9 | Sam LaPorta | DET | 6 | 10859 | 109.7 | 90.3 | 88 | -2 | **⚠ Injury question into Week 1** · Sleeper: Questionable · Career-high efficiency '25 · Carrying an injury question into Week 1; ADP standard deviation is among the widest at the position. |
| 114 | QB13 | Trevor Lawrence | JAX | 7 | 7523 | 92.5 | 86.8 | 120 | -21 | `value` · safe late, easy schedule |

## Tier 7 — ranks 115-125 (11 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 115 | WR52 | De'Zhaun Stribling | SF | 8 | 13417 | 124.4 | 110.7 | 123 | 7 | Sleeper: Questionable |
| 116 | WR53 | Khalil Shakir | BUF | 7 | 8134 | 106.3 | 131.2 | 129 | -8 | Sleeper: Questionable |
| 117 | QB14 | Jaxson Dart | NYG | 8 | 12508 | 122.9 | 104.1 | 98 | 4 | `value` · QB3 in FP/dropback '25; elite rushing; weak WRs |
| 118 | WR54 | Jalen Coker | CAR | 5 | 11646 | 114.9 | 129.7 | 135 | -1 |  |
| 119 | QB15 | Jared Goff | DET | 6 | 3163 | 101.2 | 112.0 | 124 | -15 | Leads NFL pass TDs since '22; no rush |
| 120 | WR55 | Deebo Samuel Sr. | SF | 8 | 5872 | 109.8 | 128.0 | 134 | -8 | **⚠ Sources disagree on his team - verify before drafting** · New team SF · Rotoworld still lists him as a free agent while both ADP feeds have him in San Francisco - verify his status before drafting. |
| 121 | RB42 | Josh Jacobs | GB | 11 | 5850 | 75.0 | 43.1 | 107 | -45 | **⚠ OUT INDEFINITELY - Commissioner's Exempt List** · **⚠ Sleeper: NA** · `risk` · huge ADP stdev (19.5) — uncertainty; verify status · On NFL Commissioner's Exempt List since Aug 30 - cannot practice or play, no timetable. Misdemeanor battery charges; court date Sep 10. Zero Week 1 value. |
| 122 | RB43 | Woody Marks | HOU | 8 | 12474 | 135.5 | 137.6 | 119 | 11 |  |
| 123 | WR56 | Rashid Shaheed | SEA | 11 | 8676 | 118.5 | 134.8 | 140 | -4 |  |
| 124 | RB44 | Chris Rodriguez Jr. | JAX | 7 | 10219 | 155.3 | 123.5 | 101 | 31 |  |
| 125 | QB16 | Bo Nix | DEN | 10 | 11563 | 112.0 | 106.6 | 128 | -11 | `risk` `value` · rushing; Waddle added; 4th ankle surgery |

## Tier 8 — ranks 126-145 (20 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 126 | TE10 | Travis Kelce | KC | 5 | 1466 | 132.3 | 123.7 | 122 | 2 | _late streamers_ · Route floor |
| 127 | QB17 | Kyler Murray | MIN | 6 | 5849 | 132.9 | 114.5 | 126 | 2 | `value` · named MIN starter; O'Connell scheme + Jefferson; rushing |
| 128 | TE11 | Dalton Kincaid | BUF | 7 | 10236 | 143.8 | 120.1 | 111 | 14 | Boom/bust |
| 129 | TE12 | Dallas Goedert | PHI | 10 | 5022 | 119.3 | 132.5 | 133 | -9 |  |
| 130 | RB45 | Tyjae Spears | TEN | 9 | 9508 | 137.2 | 155.3 | 131 | 4 |  |
| 131 | RB46 | Keaton Mitchell | LAC | 7 | 9511 | 156.0 | 130.1 | 117 | 25 | Sleeper: Questionable |
| 132 | RB47 | Mike Washington Jr. | LV | 13 | 13305 | 158.4 | 147.2 | 155 | 28 | `handcuff` `riser` · ✂️ handcuff for Ashton Jeanty · rookie, Jeanty insurance + standalone; "led the AFC in rushing yards (168) in the preseason while averaging 7.3 yards a carry" on 23 carries (Raiders.com); Rapoport: "is going to be a thing" (NBC, Sep 3) · Rookie 4th-rounder running with the ones while Jeanty is out. Kubiak has said he expects Washington involved even when Jeanty is healthy. |
| 133 | WR57 | Tre Tucker | LV | 13 | 10213 | 129.1 | 151.6 | 150 | -8 |  |
| 134 | TE13 | Mark Andrews | BAL | 13 | 5012 | 134.2 | 134.2 | 127 | -3 |  |
| 135 | QB18 | Jordan Love | GB | 11 | 6804 | 146.7 | 116.6 | 106 | 9 |  |
| 136 | WR58 | Jordyn Tyson | NO | 8 | 13281 | 158.8 | 90.2 | 138 | 27 | **⚠ Sleeper: IR** |
| 137 | RB48 | Tyler Allgeier | ARI | 14 | 8132 | 152.0 | 139.4 | 130 | 13 | `handcuff` |
| 138 | WR59 | Denzel Boston | CLE | 11 | 13346 | 138.1 | 142.0 | 151 | -3 |  |
| 139 | TE14 | Jake Ferguson | DAL | 14 | 8110 | 146.7 | 135.9 | 118 | 4 | `faller` · squeezed by Lamb/Pickens |
| 140 | RB49 | Jonah Coleman | DEN | 10 | 13345 | 149.1 | 143.9 | 136 | 6 |  |
| 141 | WR60 | Jalen McMillan | TB | 10 | 11618 | 132.2 | 158.2 | 154 | -14 | Sleeper: Questionable |
| 142 | QB19 | Baker Mayfield | TB | 10 | 4892 | 134.8 | 123.1 | 132 | -10 | _darts_ · Targets RBs; Egbuka |
| 143 | WR61 | Keenan Allen | IND | 13 | 1479 | 139.9 | 154.4 | 148 | -6 | `riser` · elite targets/route; hurts Pierce/Downs |
| 144 | TE15 | Isaiah Likely | NYG | 8 | 8131 | 133.7 | 126.8 | 149 | -14 | New team NYG |
| 145 | WR62 | Jauan Jennings | MIN | 6 | 7049 | 142.6 | 174.8 | 139 | -5 |  |

## Tier 9 — ranks 146-163 (18 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 146 | WR63 | Jerry Jeudy | CLE | 11 | 6783 | 126.1 | 204.3 | 169 | -23 |  |
| 147 | RB50 | Zach Charbonnet | SEA | 11 | 9753 | 139.4 | 163.5 | 167 | -11 | **⚠ Sleeper: PUP** · `handcuff` · elite pure HC |
| 148 | QB20 | Tyler Shough | NO | 8 | 12545 | 142.7 | 127.1 | 143 | -7 |  |
| 149 | TE16 | Juwan Johnson | NO | 8 | 7002 | 154.7 | 142.0 | 145 | 4 |  |
| 150 | RB51 | Braelon Allen | NYJ | 13 | 11576 | 156.1 | 185.6 | 152 | 7 |  |
| 151 | WR64 | Calvin Ridley | TEN | 9 | 4981 | 140.9 | 204.1 | 170 | -12 |  |
| 152 | QB21 | Sam Darnold | SEA | 11 | 4943 | 152.0 | 143.3 | 142 | -3 |  |
| 153 | WR65 | Malik Washington | MIA | 6 | 11610 | 148.2 | 174.5 | 172 | -8 |  |
| 154 | WR66 | Jalen Nailor | LV | 13 | 8180 | 149.1 | 152.2 | 183 | -7 |  |
| 155 | WR67 | Travis Hunter | JAX | 7 | 12530 | 161.9 | 160.6 | 146 | 18 | Has collapsed to WR60-65 across every source. Treat as a bench flier only. |
| 156 | WR68 | Ja'Kobi Lane | BAL | 13 | 13293 | 161.2 | 151.7 | 156 | 15 |  |
| 157 | RB52 | Dylan Sampson | CLE | 11 | 12469 | 166.7 | 170.0 | 137 | 23 |  |
| 158 | WR69 | Dontayvion Wicks | PHI | 10 | 9486 | 157.2 | 160.5 | 171 | 0 | _no research note_ |
| 159 | WR70 | Adonai Mitchell | NYJ | 13 | 11625 | 158.5 | 169.5 | 163 | 3 |  |
| 160 | RB53 | Brian Robinson Jr. | ATL | 11 | 8154 | 161.3 | 184.7 | 147 | 12 |  |
| 161 | TE17 | Brenton Strange | JAX | 7 | 9480 | 154.9 | 151.1 | 161 | -7 |  |
| 162 | RB54 | Emmett Johnson | KC | 5 | 13337 | 165.9 | 188.5 | 141 | 17 |  |
| 163 | WR71 | Kayshon Boutte | HOU | 8 | 9504 | 151.9 | 182.1 | 186 | -15 |  |

## Tier 10 — ranks 164-186 (23 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 164 | WR72 | Cooper Kupp | SEA | 11 | 4039 | 152.7 | 212.1 | 179 | -13 | _no research note_ |
| 165 | WR73 | Rashod Bateman | BAL | 13 | 7571 | 140.0 | 212.0 | 198 | -27 | _no research note_ |
| 166 | RB55 | Tank Bigsby | PHI | 10 | 9225 | 160.5 | 151.9 | 180 | 3 |  |
| 167 | TE18 | Hunter Henry | NE | 11 | 3214 | 160.4 | 155.1 | 157 | 1 |  |
| 168 | WR74 | Caleb Douglas | MIA | 6 | 13296 | 173.0 | 179.1 | 159 | 19 | _no research note_ |
| 169 | RB56 | Tyrone Tracy Jr. | NYG | 8 | 11655 | 160.9 | 155.8 | 189 | 1 | Sleeper: Questionable |
| 170 | RB57 | Kaleb Johnson | GB | 11 | 12504 | - | - | - | - | Acquired by Green Bay from Pittsburgh on Aug 30, the same day Josh Jacobs was placed on the exempt list. Appears in no published ranking yet. Not a draft pick in 13 rounds - make him your first waiver claim if he takes the early-down work. |
| 171 | WR75 | Ryan Flournoy | DAL | 14 | 11783 | 157.5 | 169.5 | - | -12 | _no research note_ |
| 172 | TE19 | Chig Okonkwo | WAS | 7 | 8210 | 171.1 | 148.5 | 153 | 12 |  |
| 173 | RB58 | Kaelon Black | SF | 8 | 13414 | 159.2 | 190.4 | 188 | -9 |  |
| 174 | TE20 | Dalton Schultz | HOU | 8 | 5001 | 153.8 | 161.1 | 190 | -22 |  |
| 175 | QB22 | C.J. Stroud | HOU | 8 | 9758 | 162.6 | 147.7 | 158 | -1 | `risk` · Higgins ACL hurt WR room ; sneaky value |
| 176 | WR76 | Cyrus Allen | KC | 5 | 13413 | 171.2 | 163.7 | 175 | 9 |  |
| 177 | RB59 | Isiah Pacheco | DET | 6 | 8205 | 159.3 | 191.5 | 192 | -12 | **⚠ Sleeper: IR** · `handcuff` · ✂️ handcuff for Jahmyr Gibbs · elite if Gibbs out |
| 178 | TE21 | T.J. Hockenson | MIN | 6 | 5844 | 160.2 | 168.8 | 174 | -12 | `faller` |
| 179 | WR77 | Omar Cooper Jr. | NYJ | 13 | 13276 | - | - | 144 | - |  |
| 180 | WR78 | Chris Bell | MIA | 6 | 13311 | 169.6 | 200.0 | 173 | 2 | _no research note_ |
| 181 | WR79 | Jaylin Noel | HOU | 8 | 12536 | 164.6 | 201.4 | 181 | -4 | Sleeper: Questionable · _no research note_ |
| 182 | QB23 | Daniel Jones | IND | 13 | 5870 | 163.5 | 145.1 | 166 | -6 |  |
| 183 | WR80 | DeVaughn Vele | NO | 8 | 11834 | 163.0 | 186.9 | 191 | -8 | _no research note_ |
| 184 | QB24 | Malik Willis | MIA | 6 | 8161 | 164.9 | 134.3 | 177 | -6 | `risk` · 100+ rush att projected; bad environment |
| 185 | RB60 | Ray Davis | BUF | 7 | 11575 | 160.3 | 187.0 | - | -18 |  |
| 186 | RB61 | Alvin Kamara | NO | 8 | 4035 | 158.5 | 189.3 | 193 | -25 | Sleeper: Questionable · Falling in both ADP feeds over the last two weeks. |

## Tier 11 — ranks 187-199 (13 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 187 | WR81 | Germie Bernard | PIT | 9 | 13274 | - | - | 160 | - | _no research note_ |
| 188 | WR82 | Tre Harris | LAC | 7 | 12509 | - | - | 162 | - | Sleeper: Questionable |
| 189 | WR83 | Pat Bryant | DEN | 10 | 12492 | - | - | 164 | - |  |
| 190 | WR84 | Ted Hurst | TB | 10 | 13317 | - | - | 165 | - | _no research note_ |
| 191 | WR85 | Isaac TeSlaa | DET | 6 | 12535 | 183.7 | 204.2 | 197 | -2 |  |
| 192 | WR86 | Troy Franklin | DEN | 10 | 11627 | 170.2 | 215.2 | - | -9 |  |
| 193 | RB62 | Sean Tucker | TB | 10 | 9506 | - | - | 176 | - | Sleeper: Questionable |
| 194 | RB63 | Justice Hill | BAL | 13 | 5995 | 172.2 | 213.1 | - | -8 | _no research note_ |
| 195 | WR87 | Zachariah Branch | ATL | 11 | 13320 | - | - | 178 | - |  |
| 196 | TE22 | Terrance Ferguson | LAR | 11 | 12487 | 176.3 | 158.1 | - | -8 | Sleeper: Questionable |
| 197 | RB64 | Nick Singleton | TEN | 9 | 13288 | - | - | 182 | - |  |
| 198 | RB65 | Malik Davis | DAL | 14 | 8800 | - | - | 184 | - | _no research note_ |
| 199 | WR88 | Bryce Lance | NO | 8 | 13420 | - | - | 187 | - | _no research note_ |

## Tier 12 — ranks 200-208 (9 players)

| # | Pos | Player | Tm | Bye | id | FFC | UD | RW | Δ | Notes |
|---:|---|---|---|---:|---|---:|---:|---:|---:|---|
| 200 | RB66 | Kaytron Allen | WAS | 7 | 13405 | - | - | 194 | - |  |
| 201 | QB25 | Jacoby Brissett | ARI | 14 | 3257 | 168.2 | 200.8 | - | -20 |  |
| 202 | RB67 | George Holani | SEA | 11 | 12048 | - | - | 195 | - | _no research note_ |
| 203 | TE23 | Kenyon Sadiq | NYJ | 13 | 13330 | - | - | 185 | - | Sleeper: Questionable |
| 204 | TE24 | Darren Waller | CAR | 5 | 2505 | - | 209.5 | 200 | - | _no research note_ |
| 205 | WR89 | DeMario Douglas | NE | 11 | 9501 | - | 214.0 | - | - | _no research note_ |
| 206 | TE25 | A.J. Barner | SEA | 11 | 11603 | - | - | 196 | - |  |
| 207 | QB26 | Michael Penix Jr. | ATL | 11 | 11559 | - | 212.2 | 199 | - | Sleeper: Questionable · _no research note_ |
| 208 | TE26 | Oronde Gadsden II | LAC | 7 | 12493 | - | 192.8 | 168 | - | **⚠ Buried on the depth chart - avoid** · Working behind both Charlie Kolar and David Njoku in preseason. Route share was already thin; now looks undraftable in a 13-round league. |

## Positional index

Positional rank → overall rank, for reading the runs and the cliffs.

**QB** — QB1 Josh Allen (#32, T2, bye 7) · QB2 Lamar Jackson (#54, T3, bye 13) · QB3 Drake Maye (#58, T4, bye 11) · QB4 Joe Burrow (#69, T4, bye 6) · QB5 Jayden Daniels (#70, T4, bye 7) · QB6 Jalen Hurts (#78, T5, bye 10) · QB7 Dak Prescott (#79, T5, bye 14) · QB8 Caleb Williams (#89, T5, bye 10) · QB9 Justin Herbert (#100, T6, bye 7) · QB10 Patrick Mahomes (#103, T6, bye 5) · QB11 Brock Purdy (#104, T6, bye 8) · QB12 Matthew Stafford (#106, T6, bye 11) · QB13 Trevor Lawrence (#114, T6, bye 7) · QB14 Jaxson Dart (#117, T7, bye 8) · QB15 Jared Goff (#119, T7, bye 6) · QB16 Bo Nix (#125, T7, bye 10) · QB17 Kyler Murray (#127, T8, bye 6) · QB18 Jordan Love (#135, T8, bye 11) · QB19 Baker Mayfield (#142, T8, bye 10) · QB20 Tyler Shough (#148, T9, bye 8) · QB21 Sam Darnold (#152, T9, bye 11) · QB22 C.J. Stroud (#175, T10, bye 8) · QB23 Daniel Jones (#182, T10, bye 13) · QB24 Malik Willis (#184, T10, bye 6) · QB25 Jacoby Brissett (#201, T12, bye 14) · QB26 Michael Penix Jr. (#207, T12, bye 11)

**RB** — RB1 Jahmyr Gibbs (#1, T1, bye 6) · RB2 Bijan Robinson (#2, T1, bye 11) · RB3 Christian McCaffrey (#5, T1, bye 8) · RB4 Jonathan Taylor (#7, T1, bye 13) · RB5 James Cook (#9, T1, bye 7) · RB6 De'Von Achane (#12, T1, bye 6) · RB7 Saquon Barkley (#13, T1, bye 10) · RB8 Derrick Henry (#14, T1, bye 13) · RB9 Chase Brown (#15, T1, bye 6) · RB10 Kenneth Walker III (#17, T1, bye 5) · RB11 Omarion Hampton (#21, T2, bye 7) · RB12 Ashton Jeanty (#26, T2, bye 13) · RB13 Kyren Williams (#27, T2, bye 11) · RB14 Jeremiyah Love (#28, T2, bye 14) · RB15 Javonte Williams (#31, T2, bye 14) · RB16 Breece Hall (#34, T2, bye 13) · RB17 Travis Etienne Jr. (#35, T2, bye 8) · RB18 Cam Skattebo (#41, T3, bye 8) · RB19 D'Andre Swift (#43, T3, bye 10) · RB20 Bucky Irving (#45, T3, bye 10) · RB21 Quinshon Judkins (#49, T3, bye 11) · RB22 David Montgomery (#50, T3, bye 8) · RB23 Bhayshul Tuten (#51, T3, bye 7) · RB24 TreVeyon Henderson (#59, T4, bye 11) · RB25 Jadarian Price (#60, T4, bye 11) · RB26 Jaylen Warren (#62, T4, bye 9) · RB27 Rhamondre Stevenson (#64, T4, bye 11) · RB28 Tony Pollard (#71, T4, bye 9) · RB29 Rico Dowdle (#72, T4, bye 9) · RB30 MarShawn Lloyd (#75, T5, bye 11) · RB31 J.K. Dobbins (#76, T5, bye 10) · RB32 Jonathon Brooks (#84, T5, bye 5) · RB33 Chuba Hubbard (#87, T5, bye 5) · RB34 Blake Corum (#90, T5, bye 11) · RB35 RJ Harvey (#91, T5, bye 10) · RB36 Kyle Monangai (#94, T6, bye 10) · RB37 Kenny Gainwell (#99, T6, bye 10) · RB38 Jacory Croskey-Merritt (#102, T6, bye 7) · RB39 Aaron Jones Sr. (#107, T6, bye 6) · RB40 Jordan Mason (#109, T6, bye 6) · RB41 Rachaad White (#112, T6, bye 7) · RB42 Josh Jacobs (#121, T7, bye 11) · RB43 Woody Marks (#122, T7, bye 8) · RB44 Chris Rodriguez Jr. (#124, T7, bye 7) · RB45 Tyjae Spears (#130, T8, bye 9) · RB46 Keaton Mitchell (#131, T8, bye 7) · RB47 Mike Washington Jr. (#132, T8, bye 13) · RB48 Tyler Allgeier (#137, T8, bye 14) · RB49 Jonah Coleman (#140, T8, bye 10) · RB50 Zach Charbonnet (#147, T9, bye 11) · RB51 Braelon Allen (#150, T9, bye 13) · RB52 Dylan Sampson (#157, T9, bye 11) · RB53 Brian Robinson Jr. (#160, T9, bye 11) · RB54 Emmett Johnson (#162, T9, bye 5) · RB55 Tank Bigsby (#166, T10, bye 10) · RB56 Tyrone Tracy Jr. (#169, T10, bye 8) · RB57 Kaleb Johnson (#170, T10, bye 11) · RB58 Kaelon Black (#173, T10, bye 8) · RB59 Isiah Pacheco (#177, T10, bye 6) · RB60 Ray Davis (#185, T10, bye 7) · RB61 Alvin Kamara (#186, T10, bye 8) · RB62 Sean Tucker (#193, T11, bye 10) · RB63 Justice Hill (#194, T11, bye 13) · RB64 Nick Singleton (#197, T11, bye 9) · RB65 Malik Davis (#198, T11, bye 14) · RB66 Kaytron Allen (#200, T12, bye 7) · RB67 George Holani (#202, T12, bye 11)

**WR** — WR1 Ja'Marr Chase (#3, T1, bye 6) · WR2 Jaxon Smith-Njigba (#4, T1, bye 11) · WR3 Puka Nacua (#6, T1, bye 11) · WR4 Amon-Ra St. Brown (#8, T1, bye 6) · WR5 CeeDee Lamb (#10, T1, bye 14) · WR6 Justin Jefferson (#11, T1, bye 6) · WR7 Drake London (#16, T1, bye 11) · WR8 A.J. Brown (#18, T1, bye 11) · WR9 Nico Collins (#19, T1, bye 8) · WR10 Rashee Rice (#20, T2, bye 5) · WR11 George Pickens (#22, T2, bye 14) · WR12 Malik Nabers (#23, T2, bye 8) · WR13 Chris Olave (#25, T2, bye 8) · WR14 Zay Flowers (#30, T2, bye 13) · WR15 DeVonta Smith (#33, T2, bye 10) · WR16 Tetairoa McMillan (#36, T2, bye 5) · WR17 Tee Higgins (#37, T2, bye 6) · WR18 Garrett Wilson (#38, T2, bye 13) · WR19 Ladd McConkey (#39, T3, bye 7) · WR20 Emeka Egbuka (#40, T3, bye 10) · WR21 Jaylen Waddle (#42, T3, bye 10) · WR22 Davante Adams (#44, T3, bye 11) · WR23 Jameson Williams (#46, T3, bye 6) · WR24 Terry McLaurin (#48, T3, bye 7) · WR25 Luther Burden III (#52, T3, bye 10) · WR26 Mike Evans (#53, T3, bye 8) · WR27 DJ Moore (#55, T3, bye 7) · WR28 Rome Odunze (#56, T3, bye 10) · WR29 Christian Watson (#57, T3, bye 11) · WR30 Parker Washington (#61, T4, bye 7) · WR31 Carnell Tate (#65, T4, bye 9) · WR32 Marvin Harrison Jr. (#66, T4, bye 14) · WR33 DK Metcalf (#67, T4, bye 9) · WR34 Brian Thomas Jr. (#68, T4, bye 7) · WR35 Courtland Sutton (#73, T4, bye 10) · WR36 Michael Wilson (#74, T5, bye 14) · WR37 Chris Godwin Jr. (#80, T5, bye 10) · WR38 Jayden Reed (#81, T5, bye 11) · WR39 Jordan Addison (#82, T5, bye 6) · WR40 Alec Pierce (#83, T5, bye 13) · WR41 Josh Downs (#86, T5, bye 13) · WR42 Quentin Johnston (#88, T5, bye 7) · WR43 Jakobi Meyers (#92, T6, bye 7) · WR44 Stefon Diggs (#93, T6, bye 7) · WR45 Wan'Dale Robinson (#95, T6, bye 9) · WR46 Michael Pittman Jr. (#96, T6, bye 9) · WR47 Makai Lemon (#97, T6, bye 10) · WR48 Xavier Worthy (#98, T6, bye 5) · WR49 Romeo Doubs (#101, T6, bye 11) · WR50 Matthew Golden (#108, T6, bye 11) · WR51 KC Concepcion (#111, T6, bye 11) · WR52 De'Zhaun Stribling (#115, T7, bye 8) · WR53 Khalil Shakir (#116, T7, bye 7) · WR54 Jalen Coker (#118, T7, bye 5) · WR55 Deebo Samuel Sr. (#120, T7, bye 8) · WR56 Rashid Shaheed (#123, T7, bye 11) · WR57 Tre Tucker (#133, T8, bye 13) · WR58 Jordyn Tyson (#136, T8, bye 8) · WR59 Denzel Boston (#138, T8, bye 11) · WR60 Jalen McMillan (#141, T8, bye 10) · WR61 Keenan Allen (#143, T8, bye 13) · WR62 Jauan Jennings (#145, T8, bye 6) · WR63 Jerry Jeudy (#146, T9, bye 11) · WR64 Calvin Ridley (#151, T9, bye 9) · WR65 Malik Washington (#153, T9, bye 6) · WR66 Jalen Nailor (#154, T9, bye 13) · WR67 Travis Hunter (#155, T9, bye 7) · WR68 Ja'Kobi Lane (#156, T9, bye 13) · WR69 Dontayvion Wicks (#158, T9, bye 10) · WR70 Adonai Mitchell (#159, T9, bye 13) · WR71 Kayshon Boutte (#163, T9, bye 8) · WR72 Cooper Kupp (#164, T10, bye 11) · WR73 Rashod Bateman (#165, T10, bye 13) · WR74 Caleb Douglas (#168, T10, bye 6) · WR75 Ryan Flournoy (#171, T10, bye 14) · WR76 Cyrus Allen (#176, T10, bye 5) · WR77 Omar Cooper Jr. (#179, T10, bye 13) · WR78 Chris Bell (#180, T10, bye 6) · WR79 Jaylin Noel (#181, T10, bye 8) · WR80 DeVaughn Vele (#183, T10, bye 8) · WR81 Germie Bernard (#187, T11, bye 9) · WR82 Tre Harris (#188, T11, bye 7) · WR83 Pat Bryant (#189, T11, bye 10) · WR84 Ted Hurst (#190, T11, bye 10) · WR85 Isaac TeSlaa (#191, T11, bye 6) · WR86 Troy Franklin (#192, T11, bye 10) · WR87 Zachariah Branch (#195, T11, bye 11) · WR88 Bryce Lance (#199, T11, bye 8) · WR89 DeMario Douglas (#205, T12, bye 11)

**TE** — TE1 Brock Bowers (#24, T2, bye 13) · TE2 Trey McBride (#29, T2, bye 14) · TE3 Colston Loveland (#47, T3, bye 10) · TE4 Tyler Warren (#63, T4, bye 13) · TE5 Harold Fannin Jr. (#77, T5, bye 11) · TE6 Tucker Kraft (#85, T5, bye 11) · TE7 Kyle Pitts Sr. (#105, T6, bye 11) · TE8 George Kittle (#110, T6, bye 8) · TE9 Sam LaPorta (#113, T6, bye 6) · TE10 Travis Kelce (#126, T8, bye 5) · TE11 Dalton Kincaid (#128, T8, bye 7) · TE12 Dallas Goedert (#129, T8, bye 10) · TE13 Mark Andrews (#134, T8, bye 13) · TE14 Jake Ferguson (#139, T8, bye 14) · TE15 Isaiah Likely (#144, T8, bye 8) · TE16 Juwan Johnson (#149, T9, bye 8) · TE17 Brenton Strange (#161, T9, bye 7) · TE18 Hunter Henry (#167, T10, bye 11) · TE19 Chig Okonkwo (#172, T10, bye 7) · TE20 Dalton Schultz (#174, T10, bye 8) · TE21 T.J. Hockenson (#178, T10, bye 6) · TE22 Terrance Ferguson (#196, T11, bye 11) · TE23 Kenyon Sadiq (#203, T12, bye 13) · TE24 Darren Waller (#204, T12, bye 5) · TE25 A.J. Barner (#206, T12, bye 11) · TE26 Oronde Gadsden II (#208, T12, bye 7)

## Researched but unranked

29 players with a research note that fell outside the ranked 208. Late-round and waiver material only.

| Player | Pos | Tm | id | search_rank |
|---|---|---|---|---:|
| James Conner | RB | ARI | 4137 | 92 |
| Fernando Mendoza | QB | LV | 13269 | 98 |
| Cam Ward | QB | TEN | 12522 | 104 |
| Trey Benson | RB | ARI | 11589 | 114 |
| Jayden Higgins | WR | HOU | 12484 | 126 |
| Bryce Young | QB | CAR | 9228 | 130 |
| David Njoku | TE | LAC | 4033 | 131 |
| Colby Parkinson | TE | LAR | 6865 | 136 |
| Mason Taylor | TE | NYJ | 12498 | 138 |
| Eli Stowers | TE | PHI | 13349 | 140 |
| Kimani Vidal | RB | LAC | 11647 | 141 |
| Theo Johnson | TE | NYG | 11597 | 144 |
| Cade Otton | TE | TB | 8111 | 148 |
| Gunnar Helm | TE | TEN | 12502 | 153 |
| Antonio Williams | WR | WAS | 13301 | 156 |
| Emanuel Wilson | RB | SEA | 11435 | 161 |
| Najee Harris | RB | NYG | 7528 | 170 |
| Jaylen Wright | RB | MIA | 11643 | 174 |
| Chimere Dike | WR | TEN | 12540 | 175 |
| Ben Roethlisberger | QB | PIT | 138 | 176 |
| Demond Claiborne | RB | MIN | 13347 | 176 |
| Brandon Aiyuk | WR | SF | 6803 | 177 |
| Jake Tonges | TE | SF | 8698 | 178 |
| Kendre Miller | RB | NO | 9757 | 180 |
| Brashard Smith | RB | KC | 12455 | 182 |
| Elic Ayomanor | WR | TEN | 12499 | 185 |
| Tank Dell | WR | HOU | 9502 | 187 |
| Jaydon Blue | RB | PHI | 12457 | 189 |
| Audric Estime | RB | NO | 11579 | 190 |

## Provenance

**Player pool** — QB/RB/WR/TE only - this league has NO kicker and NO defense slots

**Method** — Each source converted to a rank, blended on the weights above, then adjusted for (a) this league's roster structure and (b) news that postdates one or more sources. A soft penalty is applied at half weight when a source omits a player rather than dropping the signal.

**Sources**

| Source | Date | Weight | Why |
|---|---|---|---|
| Fantasy Football Calculator 12-team half-PPR redraft ADP | 2026-09-05 | 0.45 | Exact format match and the most current market read. |
| Rotoworld / NBC Sports Top 200 expert rankings | 2026-09-04 | 0.35 | Human expert judgment; reacts to news faster than ADP. Note their team labels are stale in places (they still list A.J. Brown on PHI and Deebo Samuel as a free agent). |
| Underdog best-ball half-PPR ADP (via Sharp Football) | 2026-08-28 | 0.2 | Second independent market. Down-weighted because best ball inflates QB/TE and upside rookies, and it predates the Aug 30 Josh Jacobs news. |
| PFF half-PPR top 200 (Nathan Jahnke) | 2026-08-18 | reference only | Paywalled beyond the headline; used as a sanity check (Gibbs 1, Nacua WR1, Allen QB1 at 31, Bowers TE1 at 27). |

**Draft mechanics** — Round 1 runs 1->12, round 2 runs 12->1, and round 3 ALSO runs 12->1 instead of flipping back. Normal snake resumes in round 4. The practical effect is that the reversal transfers value toward the back of round 1: slot 12 picks at 12, 13 and 25, while slot 1 picks at 1, 24 and 36.

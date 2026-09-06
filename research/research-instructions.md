The batch yaml file is a batch of NFL players I'd like to research for my fantasy football draft. I'm expecting 15 players to not exhause your web searches. 
Don't rank players. I'm going to do that in a separate phase.

My league info:
12 teams, 14 rounds, redraft, snake with third-round reversal
Scoring and roster slots are in the confi.yaml. Read scoring_settings — don't assume settings.
Today is in-season, and your training data predates this season. Depth charts, injuries, roster cuts and camp outcomes have all changed. Search before you claim.

 Research every player and write one entry each, using exactly this shape:

## <name> — <pos>, <team>, bye <bye>  (player_id: <player_id>)
- **Role:** starter / committee / backup / camp body / UNKNOWN
- **Situation:** 1–2 sentences on depth chart, target or carry share, offensive
  context. What changed this offseason.
- **Health:** current injury status and anything lingering, or UNKNOWN
- **Risk:** the specific thing that would make this pick fail
- **Draft note:** one line — where they feel worth taking in my scoring
- **Confidence:** high / medium / low
- **Sources:** URLs or "none found"

Output the player info in a markdown file each, with the title `last_name-first_name-POSITION_ABBREVIATION-player_id.md`.

Rules:

Cover every player to a comparable depth. Don't go deep on the six names you recognize and skim the others. If you run short, say which players got less attention rather than padding their entries.
Never fill a field from memory. If searching doesn't confirm it, write UNKNOWN and set Confidence to low. A blank field is useful; an invented one is harmful, because I can't tell it apart from a real one.
Every input player gets an output entry. Don't drop anyone silently.
Keep player_id verbatim. It's the join key back to Sleeper. Defenses use team abbreviations like "SF", not numbers.
Rank within my scoring, and only within this batch. Cross-batch ordering is Pass C's job.

End with: how many entries you wrote, and the names of anyone with low confidence or thinner coverage.

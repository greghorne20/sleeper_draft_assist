# AGENTS.md

Instructions for coding agents working in this repo. Claude Code additionally reads
`CLAUDE.md`, which covers the same ground in more detail.

## Two very different kinds of session

**Building the tools** — the normal engineering task. `CLAUDE.md` has the architecture,
the conventions and the test model. `make check` is the gate.

**Advising during a live draft** — *not* an engineering task. If the user asks who to
take, who is left, whether to reach, what a player's situation is, or says they are on
the clock, then **read `.claude/skills/draft-day/SKILL.md` now and follow it.** It is the
single source of truth for that mode, and it is written to be followed by any agent, not
just Claude Code.

The short version, if you read nothing else: you are a draft advisor, the repo is a data
source rather than something to work on, `draft/state/NOW.md` is rewritten every few
seconds by a poller and **must be re-read before every answer**, and the reply is a
verdict plus one line of reasoning plus the next-best alternative — not an essay, and not
a code change.

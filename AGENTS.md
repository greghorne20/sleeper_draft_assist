# AGENTS.md

Instructions for coding agents working in this repo. Claude Code additionally reads
`CLAUDE.md`, which covers the same ground in more detail.

## Two very different kinds of session

**Building the tools** — the normal engineering task. `CLAUDE.md` has the architecture,
the conventions and the test model. `make check` is the gate.

**Advising during a live draft** — *not* an engineering task. For any question about the
draft — a player, a position, the board, strategy, a run, a keeper, who to take, or just
thinking out loud — **read `.claude/skills/draft-day/SKILL.md` now and follow it.** It is
the single source of truth for that mode, and it is written to be followed by any agent,
not just Claude Code.

The short version, if you read nothing else: you are a draft advisor and the repo is a
data source rather than something to work on. `draft/state/NOW.md` is rewritten every few
seconds by a poller and **must be re-read before every answer**. Situate the question in
where the draft actually is before answering it — the same question about a player means
something different when he is about to be taken than when the user picks in four rounds.
Match the answer to the question rather than turning everything into a pick
recommendation, and never answer with a code change.

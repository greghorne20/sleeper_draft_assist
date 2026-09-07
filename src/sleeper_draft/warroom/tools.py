#!/usr/bin/env python3
"""The two things a war room reaches for beyond what is already in its prompt.

These are exactly what `.claude/skills/draft-day/SKILL.md` tells a Claude Code
session to do with Read and Grep, as callables: read one player's research note,
and look further down the board than the top thirty.

NEITHER OF THEM PARSES ANYTHING
    `board_rows` reads `board.json`, and `read_player_note` hands over a whole
    document. That is the same direction the rest of the repo runs -- board.md is
    generated from board.json, NOW.md from the state, keepers.md from
    keepers.json -- and slicing a hand-written document with a regex to find a
    heading would have been the one place going the other way. STRATEGY.md's
    reasoning is what the conversational draft-day session is for; a four-field
    brief needs the doctrine, which is in the system prompt.

WHY THERE IS NO agent_framework IMPORT HERE
    Agent Framework accepts any annotated Python callable as a function tool, so
    keeping this module framework-free means the tools are testable with the rest
    of the offline suite and the repo's core install still needs nothing but
    PyYAML. `agent.py` is the only place that imports the framework.

WHY THESE ARE READ-ONLY AND NEED NO APPROVAL
    Every one of them reads a file this repo generated, under paths the caller
    supplies. Nothing is written, nothing is fetched, and no path comes from the
    model -- `read_player_note` takes a player_id and looks the path up on the
    board rather than joining anything the model said onto a directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Callable

from ..board import market_adp

# How many board rows one `board_rows` call may return. A war room that asks for
# the whole board has stopped using the prompt it was given.
MAX_ROWS = 40


def _row_line(row: dict) -> str:
    adp = market_adp(row)
    bits = [
        f"#{row['rank']}",
        row["pos_rank"],
        row["name"],
        row["team"] or "-",
        f"bye {row['bye']}",
        f"id {row['player_id']}",
        f"ADP {'-' if adp is None else adp}",
        f"tier {row['tier']}",
    ]
    if row.get("risk_flag"):
        bits.append(f"RISK {row['risk_flag']}")
    if row.get("sleeper_injury_status"):
        bits.append(str(row["sleeper_injury_status"]))
    if row.get("flags"):
        bits.append(" ".join(row["flags"]))
    if row.get("handcuff_for_name"):
        bits.append(f"handcuff for {row['handcuff_for_name']}")
    if row.get("scouting"):
        bits.append(str(row["scouting"]))
    return " · ".join(str(b) for b in bits)


def build_tools(board: dict, available: dict[str, dict]) -> list[Callable[..., str]]:
    """The tool set for one generation, bound to this poll's board and state.

    `available` is rebound every generation so a tool can never hand back a
    player who has already been drafted -- the same guarantee `validate_brief`
    enforces on the way out, applied on the way in.
    """
    by_id = {row["player_id"]: row for row in board["players"]}

    def read_player_note(
        player_id: Annotated[str, "The Sleeper player_id exactly as it appears on the board"],
    ) -> str:
        """Read the full research note for one player.

        Use this before recommending anyone, so the reasoning comes from the
        research rather than from memory. Returns the scouting line and board row
        if no note was written for that player.
        """
        row = by_id.get(player_id)
        if row is None:
            return (
                f"No player with id {player_id!r} is on the board. Use an id from the "
                "board rows you were given, or from board_rows."
            )
        header = _row_line(row)
        note = row.get("research_note")
        if not note:
            return f"{header}\n\n(No research note was written for this player.)"
        path = Path(note)
        if not path.exists():
            return f"{header}\n\n(Research note {note} is missing from disk.)"
        return f"{header}\n\n{path.read_text()}"

    def board_rows(
        pos: Annotated[str, "QB, RB, WR, TE, or ALL for every position"] = "ALL",
        start_rank: Annotated[
            int, "Overall rank to start from; the prompt already shows the top of the board"
        ] = 1,
        limit: Annotated[int, f"How many rows to return, at most {MAX_ROWS}"] = 20,
    ) -> str:
        """List available players from the ranked board, deeper than the prompt shows.

        Only players still on the board are returned, so anything here is a legal
        recommendation. Use it for late-round targets, handcuffs, and to see how
        thin a position has gone.
        """
        wanted = pos.strip().upper()
        rows = [
            row
            for row in board["players"]
            if row["player_id"] in available
            and row["rank"] >= max(1, start_rank)
            and (wanted in ("ALL", "") or row["pos"].upper() == wanted)
        ]
        if not rows:
            return (
                f"No available players match pos={pos!r} from rank {start_rank}. "
                f"{len(available)} players are still on the board."
            )
        capped = rows[: max(1, min(limit, MAX_ROWS))]
        head = f"{len(rows)} available at pos={wanted} from rank {start_rank}; showing {len(capped)}."
        return head + "\n" + "\n".join(_row_line(row) for row in capped)

    return [read_player_note, board_rows]

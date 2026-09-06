#!/usr/bin/env python3
"""The war-room brief: its shape, and every decision that does not need a model.

Everything in this module is pure. That is deliberate and it is the same split
`live.summarize()` and `keepers.eligible_keepers()` make: the parts that decide
*what is true* are testable without a network, and the model is only asked for
the part that genuinely needs judgement.

Three things live here:

VALIDATION
    `validate_brief` is the correctness gate. The worst failure this layer can
    have is recommending a player who is already gone, so model output is checked
    against the board the same way `board.py` checks a rankings row -- and an
    invalid brief is refused rather than shown.

THE TRIGGER
    `refresh_targets` decides which of the twelve rooms a new pick actually
    invalidates. Regenerating a brief for a team forty picks away is work nobody
    reads, so the default is to regenerate the rooms where the answer changed.

THE PROMPT
    `build_prompt` assembles one seat's situation from state that is already
    computed. It carries the previous brief's plan forward so a room has a
    standing strategy that gets amended, rather than a fresh opinion every pick.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..live import _player_table, team_label

# Positions this league has no roster slot for. PLAYBOOK: "No kicker slot. No
# defense slot." A brief naming one is rejected, not rendered.
FORBIDDEN_POSITIONS = ("K", "DEF", "DST")

# How close a room has to be to its next pick before every single pick
# regenerates it. Five rather than three: a room five out is already being read,
# and the whole-draft bill is the constraint that sets this -- ~$69 simulated
# against ~$49 at three, which is headroom this league has.
HOT_WITHIN = 5

# A room nowhere near its turn still refreshes this often, so no tab goes stale.
COLD_EVERY = 4


class Candidate(BaseModel):
    """One recommended player. `why` has to come from the board or the note."""

    # Anthropic's structured-output endpoint refuses an object schema that does
    # not set additionalProperties: false, and `extra="forbid"` is what makes
    # Pydantic emit it. It also means a stray field is a validation error rather
    # than something that reaches the page unnoticed.
    model_config = ConfigDict(extra="forbid")

    player_id: str = Field(description="Sleeper player_id, exactly as it appears on the board")
    name: str = Field(description="Player name, exactly as the board spells it")
    pos: str = Field(description="QB, RB, WR or TE")
    why: str = Field(description="One or two sentences grounded in the board row or research "
                                 "note. Name the PLAYBOOK rule if one is doing the work.")


class Brief(BaseModel):
    """What one war room shows. The model fills this; code adds the provenance."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = Field(description="Where this team stands and the plan for its next two or "
                                      "three picks. Amend the standing plan rather than "
                                      "replacing it; say what changed.")
    pick: Candidate = Field(description="The recommendation right now")
    alternative: Candidate = Field(description="Next best, and in `why` say what would flip it")
    watch: list[str] = Field(default_factory=list,
                             description="player_ids likely gone before this team picks again")
    risks: list[str] = Field(default_factory=list,
                             description="Bye stacks, positional holes, injury flags. Short.")


def drafted_ids(all_state: dict) -> set[str]:
    """Every player already taken.

    `rosters_by_slot` holds every pick grouped by seat -- off-board picks
    included, since those are recorded against a slot like any other -- so the
    drafted set falls out of state the poller already writes.
    """
    return {entry["player_id"]
            for picks in (all_state.get("rosters_by_slot") or {}).values()
            for entry in picks
            if entry.get("player_id")}


def available_index(board: dict, all_state: dict) -> dict[str, dict]:
    """player_id -> board row, for everyone still on the board.

    The prompt only shows the top thirty, but the agent can reach further with
    the `board_rows` tool, so validation has to accept anyone still available --
    a round-11 handcuff is a legitimate recommendation.
    """
    taken = drafted_ids(all_state)
    return {row["player_id"]: row for row in board["players"]
            if row["player_id"] not in taken}


def validate_brief(brief: Brief, available: dict[str, dict]) -> list[str]:
    """Everything wrong with a brief, named. Empty means it can be shown.

    Fails loud in the repo's usual style rather than quietly dropping a bad
    field: a brief that recommends a drafted player is worse than no brief,
    because it reads exactly like a good one.
    """
    problems: list[str] = []

    for slot, candidate in (("pick", brief.pick), ("alternative", brief.alternative)):
        row = available.get(candidate.player_id)
        if row is None:
            problems.append(
                f"{slot}: player_id {candidate.player_id!r} ({candidate.name}) is not available "
                "-- he is already drafted or not on the board."
            )
            continue
        if row["name"].casefold() != candidate.name.casefold():
            problems.append(
                f"{slot}: player_id {candidate.player_id!r} is {row['name']}, not "
                f"{candidate.name!r}. Use the board's id and name together."
            )
        if row["pos"].upper() in FORBIDDEN_POSITIONS:
            problems.append(f"{slot}: {row['name']} is a {row['pos']}; this league has no such slot.")
        if candidate.pos.upper() in FORBIDDEN_POSITIONS:
            problems.append(f"{slot}: pos {candidate.pos!r} -- this league has no kicker or "
                            "defense slot.")

    if brief.pick.player_id == brief.alternative.player_id:
        problems.append("pick and alternative are the same player; the alternative has to differ.")

    for pid in brief.watch:
        if pid not in available:
            problems.append(f"watch: {pid!r} is not an available player_id.")

    return problems


def room_for(briefs: dict, slot: int) -> dict | None:
    return (briefs.get("rooms") or {}).get(str(slot))


def hot_slots(all_state: dict, hot_within: int = HOT_WITHIN) -> set[int]:
    """Seats close enough to their turn that someone is reading the brief.

    Two decisions hang off this one definition, and they should not drift apart:
    which rooms regenerate on every pick, and which get the better model. A room
    forty picks out is being glanced at; a room on the clock is being acted on.
    """
    current = all_state.get("current_pick")
    if current is None:
        return set()
    hot = set()
    for key, room in (all_state.get("war_rooms") or {}).items():
        next_pick = (room or {}).get("my_next_pick")
        if next_pick is not None and next_pick - current <= hot_within:
            hot.add(int(key))
    return hot


def refresh_targets(all_state: dict, briefs: dict, hot_within: int = HOT_WITHIN,
                    cold_every: int = COLD_EVERY, mode: str = "hot") -> set[int]:
    """Which rooms this pick actually invalidated.

    `mode="all"` regenerates every seat on every pick, which is the literal
    reading of "update when a pick lands" and costs about four times as much.
    The default asks a narrower question: for whom did the answer change?

    A room regenerates when it has no brief, when its brief errored, when it is
    close enough to its turn that someone is reading it, when it just picked,
    when the player it proposed has since been taken -- that is the staleness
    that misleads -- or when its brief has simply aged out.
    """
    rooms = all_state.get("war_rooms") or {}
    slots = {int(key) for key in rooms}
    if mode == "all":
        return slots

    picks_made = all_state.get("picks_made") or 0
    taken = drafted_ids(all_state)
    recent = all_state.get("recent_picks") or []
    just_picked = recent[-1].get("draft_slot") if recent else None

    hot = hot_slots(all_state, hot_within)

    targets: set[int] = set()
    for slot in slots:
        brief = room_for(briefs, slot)
        if brief is None or brief.get("status") == "error":
            targets.add(slot)
            continue
        if slot == just_picked or slot in hot:
            targets.add(slot)
            continue

        proposed = ((brief.get("pick") or {}).get("player_id"))
        if proposed and proposed in taken:
            targets.add(slot)
            continue

        if picks_made - (brief.get("picks_made") or 0) >= cold_every:
            targets.add(slot)
    return targets


def _roster_block(seat: dict) -> list[str]:
    out = ["## Your roster", ""]
    roster = seat.get("my_roster") or []
    if not roster:
        out += ["Nothing drafted yet.", ""]
    else:
        out += ["| Pick | Rd | Player | Pos | Tm | Bye | Tier |",
                "|---:|---:|---|---|---|---:|---:|"]
        out += [f"| {p['pick_no']} | {p['round']} | {p['name']} | {p['pos']} | {p['team']} | "
                f"{p['bye'] or '-'} | {p['tier'] or '-'} |" for p in roster]
        out.append("")

    need = seat.get("roster") or {}
    counts = " · ".join(f"{pos} {n}" for pos, n in sorted((need.get("counts") or {}).items()))
    gaps = list(need.get("open_starters") or []) + (["FLEX"] if need.get("flex_open") else [])
    out.append(f"**Have:** {counts or 'empty'}")
    out.append(f"**Starting slots still open:** {', '.join(gaps) if gaps else 'none'}")
    heavy = sorted((week for week, n in (seat.get("bye_counts") or {}).items() if n >= 3), key=int)
    if heavy:
        out.append("**Bye stack:** " + ", ".join(f"week {w}" for w in heavy)
                   + " — PLAYBOOK caps this at 2 projected starters per bye week.")
    out.append("")
    return out


def _league_block(all_state: dict, my_slot: int) -> list[str]:
    """What rivals still need. Colour, and labelled as such.

    Twelve rooms reading each other's needs and all reaching a round early is a
    feedback loop that market ADP does not have, so this block says outright that
    it is not an input to the survival question.
    """
    out = ["## Around the league (context, not an urgency input)", ""]
    for key in sorted(all_state.get("war_rooms") or {}, key=int):
        room = all_state["war_rooms"][key]
        need = room.get("roster") or {}
        counts = " ".join(f"{pos}{n}" for pos, n in sorted((need.get("counts") or {}).items()))
        gaps = list(need.get("open_starters") or []) + (["FLEX"] if need.get("flex_open") else [])
        mine = " ← you" if int(key) == my_slot else ""
        out.append(f"- **{room.get('name')}** — has {counts or 'nothing'} — "
                   f"needs {' '.join(gaps) if gaps else 'nothing, starters set'}{mine}")
    out += ["",
            "Use this to read the room, not to decide who survives. Whether a player lasts is the "
            "`Gone by` column, which is market ADP measured over thousands of drafts. Do not "
            "reach a round early because several rivals share a need.",
            ""]
    return out


def build_prompt(seat: dict, all_state: dict, previous: dict | None = None) -> str:
    """One seat's whole situation, assembled from state already computed."""
    slot = seat["my_slot"]
    out: list[str] = []
    out.append(f"# War room — {seat.get('my_team_name') or f'slot {slot}'} (draft slot {slot})")
    out.append("")
    out.append(f"{all_state.get('league_name')} · {all_state['teams']} teams · "
               f"{all_state['rounds']} rounds · roster "
               f"{', '.join(all_state.get('roster_positions') or [])}")
    out.append("")

    out.append("## Where the draft is")
    out.append("")
    if seat["current_pick"] is None:
        out.append("The draft is complete.")
    else:
        out.append(f"- Pick {seat['current_pick']} of {seat['total_picks']}, round "
                   f"{seat['current_round']}. On the clock: "
                   f"{team_label(seat, seat['on_the_clock_slot'])}.")
        if seat["is_my_turn"]:
            out.append("- **You are on the clock. This pick is being made now.**")
        if seat["my_next_pick"]:
            out.append(f"- Your next pick: **{seat['my_next_pick']}**"
                       + (f", then {seat['my_pick_after_next']}."
                          if seat["my_pick_after_next"] else " (your last)."))
        if seat["survive_until_pick"]:
            out.append(f"- **{seat['picks_before_horizon']} picks by other teams** before pick "
                       f"{seat['survive_until_pick']} comes back to you. A player has to survive "
                       "all of them to still be there.")
    out.append("")

    out += _roster_block(seat)

    horizon = seat.get("survive_until_pick")
    shown = seat.get("best_available") or []
    out.append(f"## Best available — top {len(shown)} of {seat['available_count']} left")
    out.append("")
    if horizon:
        out.append(f"`Gone by {horizon}?` is market ADP within {seat['cushion']} of that pick. "
                   "PLAYBOOK D1: prefer the highest-value player who will NOT survive over one "
                   "who will.")
        out.append("")
    out += _player_table(shown, horizon)
    out.append("")

    out.append("## Tiers remaining")
    out.append("")
    out.append("PLAYBOOK D2: take the last man in a tier when the count drops to the number of "
               "teams drafting before you return.")
    for pos in ("RB", "WR", "TE", "QB"):
        tiers = (seat.get("tier_status") or {}).get(pos)
        if tiers:
            out.append(f"- **{pos}** — " + " · ".join(f"T{t} {tiers[t]}"
                                                      for t in sorted(tiers, key=int)))
    out.append("")

    recent = seat.get("recent_picks") or []
    if recent:
        run = " · ".join(f"{pos} {n}" for pos, n in
                         sorted((seat.get("position_run") or {}).items(), key=lambda kv: -kv[1]))
        out.append(f"## Last {len(recent)} picks — run: {run}")
        out.append("")
        for entry in reversed(recent):
            who = "you" if entry["draft_slot"] == slot else team_label(seat, entry["draft_slot"])
            kept = " (keeper)" if entry.get("is_keeper") else ""
            out.append(f"- `{entry['pick_no']}` {who}: {entry['name']} "
                       f"({entry['pos']}, {'#' + str(entry['rank']) if entry['rank'] else 'unranked'})"
                       f"{kept}")
        out.append("")

    out += _league_block(all_state, slot)

    if previous and previous.get("strategy"):
        out.append(f"## Your standing plan (written at pick {previous.get('picks_made', '?')})")
        out.append("")
        out.append(previous["strategy"])
        out.append("")
        out.append("Amend this rather than starting over. Say what changed since. If nothing "
                   "material changed, keep the plan and say so plainly.")
        out.append("")

    out.append("## Now write the brief")
    out.append("")
    out.append("Use `read_player_note` before recommending anyone you have not already justified "
               "— the reasoning has to come from the research, not from memory. Use `board_rows` "
               "to look past the top of the board, and `read_strategy_section` when you need the "
               "reasoning behind a rule. Every player_id you name must appear on the board above "
               "or come back from `board_rows`.")
    return "\n".join(out)


def render_brief_md(room: dict) -> str:
    """One room's brief as markdown, so it reads with `cat` like everything else."""
    out = [f"# War room — {room.get('name')} (slot {room.get('slot')})", ""]
    status = room.get("status")
    stamp = (f"_As of pick {room.get('picks_made')} · written {room.get('generated_at')}"
             f" · {room.get('model', 'unknown model')}_")
    out += [stamp, ""]
    if status == "error":
        out += ["> **⚠ This brief could not be regenerated and is the previous one.** "
                + str(room.get("error") or ""), ""]

    if not room.get("strategy"):
        out += ["_No brief yet._", ""]
        return "\n".join(out)

    out += ["## Strategy", "", room["strategy"], ""]

    for heading, key in (("The pick", "pick"), ("Instead", "alternative")):
        candidate = room.get(key) or {}
        if candidate:
            out += [f"## {heading} — {candidate.get('name')} "
                    f"({candidate.get('pos')}, `{candidate.get('player_id')}`)", "",
                    str(candidate.get("why") or ""), ""]

    if room.get("watch_names"):
        out += ["## Watch", "",
                "Likely gone before this team picks again: "
                + ", ".join(room["watch_names"]), ""]
    if room.get("risks"):
        out += ["## Risks", ""] + [f"- {risk}" for risk in room["risks"]] + [""]
    return "\n".join(out)


def render_briefs_md(briefs: dict) -> str:
    """Every room in one document, for reading the league at a glance."""
    out = [f"# War rooms — pick {briefs.get('picks_made')}", "",
           f"_{briefs.get('generated_at')} · {briefs.get('model')}_", ""]
    for key in sorted(briefs.get("rooms") or {}, key=int):
        room = briefs["rooms"][key]
        pick = room.get("pick") or {}
        out.append(f"- **{room.get('name')}** (slot {key}) — "
                   + (f"{pick.get('name')} ({pick.get('pos')})" if pick else "no brief yet")
                   + (f" · _stale, from pick {room.get('picks_made')}_"
                      if room.get("picks_made") != briefs.get("picks_made") else ""))
    out.append("")
    for key in sorted(briefs.get("rooms") or {}, key=int):
        out += [render_brief_md(briefs["rooms"][key]), "---", ""]
    return "\n".join(out)


def new_room(seat: dict, all_state: dict, brief: Brief | None, *, model: str,
             status: str = "ok", error: str | None = None,
             usage: dict | None = None, available: dict[str, dict] | None = None) -> dict:
    """A brief plus the provenance the model is not asked for and cannot forge."""
    slot = seat["my_slot"]
    room: dict[str, Any] = {
        "slot": slot,
        "name": seat.get("my_team_name") or team_label(seat, slot),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "picks_made": all_state.get("picks_made"),
        "for_pick": seat.get("my_next_pick"),
        "model": model,
        "status": status,
    }
    if error:
        room["error"] = error
    if usage:
        room["usage"] = usage
    if brief is not None:
        room["strategy"] = brief.strategy
        room["pick"] = brief.pick.model_dump()
        room["alternative"] = brief.alternative.model_dump()
        room["watch"] = list(brief.watch)
        room["risks"] = list(brief.risks)
        # Ids are the join key, but a reader wants names.
        index = available or {}
        room["watch_names"] = [index.get(pid, {}).get("name", pid) for pid in brief.watch]
    return room

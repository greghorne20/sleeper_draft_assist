#!/usr/bin/env bash
#
# Supervise the poller and the war room.
#
# Both are long-running and neither may take the other down. The poller is the
# one that matters: it serves the page and rebuilds the whole state every ten
# seconds, so if it dies the board goes dark. The war room is optional by
# design -- no API key, or a crash loop, and the page simply renders without the
# brief panel.
#
# Restarts are unconditional and cheap because the state is derived. A poller
# that comes back rebuilds everything in one cycle; a war room that comes back
# regenerates briefs because refresh_targets treats "no brief" as "regenerate".

set -uo pipefail

: "${PORT:=8765}"
: "${HOST:=0.0.0.0}"
: "${POLL_INTERVAL:=10}"
: "${RESTART_DELAY:=5}"

log() { printf '[%s] %s\n' "$1" "${*:2}" >&2; }

# --- the artifacts have to be baked in; sleeper-board is a build step ---------
for required in draft/board.json draft/pick_order.json; do
    if [[ ! -f "$required" ]]; then
        log entrypoint "FATAL: $required is missing from the image."
        log entrypoint "Run 'uv run sleeper-board' and commit the result before building."
        exit 1
    fi
done

children=()

shutdown() {
    log entrypoint "signal received, stopping children"
    for pid in "${children[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    wait
    exit 0
}
trap shutdown TERM INT

# Restart forever, but never faster than RESTART_DELAY -- a process that fails
# instantly must not become a hot loop against Sleeper or the Anthropic API.
supervise() {
    local name=$1
    shift
    while true; do
        log "$name" "starting: $*"
        "$@"
        log "$name" "exited with $?; restarting in ${RESTART_DELAY}s"
        sleep "$RESTART_DELAY"
    done
}

# --- the poller: owns the Sleeper API and serves the page --------------------
live_args=(sleeper-live --watch --serve --host "$HOST" --port "$PORT"
           --interval "$POLL_INTERVAL")
[[ -n "${SLEEPER_SLOT:-}" ]] && live_args+=(--slot "$SLEEPER_SLOT")
[[ -n "${SLEEPER_DRAFT_ID:-}" ]] && live_args+=(--draft-id "$SLEEPER_DRAFT_ID")

supervise live "${live_args[@]}" &
children+=($!)

# --- the war room: optional, and silent about it -----------------------------
# Starting it without a key would be a restart loop that logs an error every
# five seconds and produces nothing, so check first and say why.
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    warroom_args=(sleeper-warroom --watch)
    [[ -n "${ANTHROPIC_CHAT_MODEL:-}" ]] && warroom_args+=(--model "$ANTHROPIC_CHAT_MODEL")
    [[ -n "${WARROOM_REFRESH:-}" ]] && warroom_args+=(--refresh "$WARROOM_REFRESH")
    supervise warroom "${warroom_args[@]}" &
    children+=($!)
else
    log entrypoint "ANTHROPIC_API_KEY is not set -- war room disabled, board unaffected."
fi

log entrypoint "serving on ${HOST}:${PORT} with ${#children[@]} process(es)"
wait

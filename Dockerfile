# The live draft board and its twelve war rooms, as one image.
#
# TWO PROCESSES, ONE CONTAINER
#     sleeper-live polls Sleeper and serves the page; sleeper-warroom writes the
#     briefs. They communicate only through draft/state/ on the filesystem, which
#     is the whole design (see serve.py), so splitting them across containers
#     would mean a shared volume for no benefit -- neither scales independently.
#     docker-entrypoint.sh supervises both.
#
# NO VOLUME, ON PURPOSE
#     Everything under draft/state/ is derived and rewritten every poll. A
#     restart mid-draft rebuilds the whole state in one cycle, and briefs
#     regenerate because refresh_targets treats "no brief" as "regenerate". So
#     this image is stateless and needs no persistence of any kind.
#
# WHAT IS NOT IN HERE
#     No players dump. Nothing at runtime calls /players/nfl -- the board already
#     resolved every name to a player_id -- so there is no 5MB cache to warm and
#     no cold-start download. Runtime inputs are about 1.2MB.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Dependencies first, so editing source does not re-resolve the world.
# --frozen honours uv.lock rather than re-solving; --no-dev leaves out pytest,
# ruff and mypy. pydantic arrives through the warroom extra, not the dev group.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra warroom --no-install-project

# The code, then the artifacts it reads. draft/ supplies board.json,
# pick_order.json and PLAYBOOK.md; research/players holds the notes the war
# room's read_player_note tool serves back.
COPY src/ src/
COPY draft/ draft/
COPY research/ research/
RUN uv sync --frozen --no-dev --extra warroom

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# The platform injects PORT and routes to it; 8765 is only the local default.
ENV PORT=8765 \
    HOST=0.0.0.0
EXPOSE 8765

# Python rather than curl: the slim base has no curl and adding one for a
# healthcheck is a layer for nothing. "/" is the right path -- /state.json
# legitimately 404s until the first poll lands, so checking it would fail the
# deploy during the twenty seconds when everything is working correctly.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8765') + '/', timeout=4)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Task runner for the Sleeper draft tools. Every target is a thin wrapper over a
# `uv run` command -- nothing here does work the console scripts do not.
#
# Draft-day targets take variables:  make live SLOT=12
#
# Requires GNU make (`sudo apt install make` on a bare WSL/Debian box).

LEAGUE ?= $(shell sed -n "s/^league_id: *'\?\([0-9]*\)'\?/\1/p" config.yaml 2>/dev/null)
SLOT   ?=
PORT   ?= 8765
BYES   ?= byes.2026.json

# Passed through to sleeper-live; empty SLOT means the pick-timing maths is
# skipped rather than guessed, which is live.py's own documented behaviour.
SLOT_ARG = $(if $(SLOT),--slot $(SLOT),)

.DEFAULT_GOAL := help
.PHONY: help setup check lint types test fmt-check board keepers live watch discover past-draft batches clean

help:  ## Show this help
	@echo "Sleeper draft tools"
	@echo
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variables:  SLOT=12  LEAGUE=<id>  PORT=8765  BYES=byes.2026.json"
	@echo "League id defaults to the one in config.yaml ($(LEAGUE))"

setup:  ## Create .venv and install the package + dev group
	uv sync

# ---------------------------------------------------------------- quality

check: lint types test  ## Lint, type-check and test -- run this before committing

lint:  ## ruff check
	uv run ruff check .

types:  ## mypy over src/
	uv run mypy

test:  ## The offline test suite (no test touches the network)
	uv run pytest -q

fmt-check:  ## Report what ruff format WOULD change (not adopted -- see README)
	uv run ruff format --check --diff .

# ---------------------------------------------------------------- artifacts

discover:  ## Refresh config.yaml from Sleeper
	uv run sleeper-discover --league-id $(LEAGUE) --out config.yaml

board:  ## Rebuild draft/board.{md,json} and pick_order.json
	uv run sleeper-board

keepers:  ## Rebuild draft/keepers.{md,json} from last season
	uv run sleeper-keepers --league-id $(LEAGUE)

batches:  ## Rebuild the research batches
	uv run sleeper-batches --byes $(BYES)

past-draft:  ## Save last season's draft as a fixture
	uv run sleeper-past-draft --league-id $(LEAGUE) --back 1

# ---------------------------------------------------------------- draft day

live:  ## One poll + serve the live page (make live SLOT=12)
	uv run sleeper-live $(SLOT_ARG) --serve --port $(PORT)

watch:  ## Poll until the draft ends, serving the page (make watch SLOT=12)
	uv run sleeper-live $(SLOT_ARG) --watch --serve --port $(PORT)

clean:  ## Remove the live state files (regenerated every poll)
	rm -rf draft/state

"""Read a .env file into the environment. One place so every command agrees.

The CLIs default their arguments from environment variables at parse time --
`default=os.environ.get("SLEEPER_LEAGUE_ID")` and friends -- so this has to run
before parse_args() builds the parser, not after.

Written by hand rather than pulling python-dotenv: it is ten lines, it must work
on a machine where the optional warroom extra was never installed, and the whole
repo runs on PyYAML alone.

Anything already exported wins, so a real environment variable is never silently
overridden by a stale file. That is also what keeps Railway (which sets real env
vars and ships no .env) behaving the same as a laptop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_FILE_VAR = "SLEEPER_ENV_FILE"
DEFAULT_ENV_FILE = ".env"


def load_env_file(path: Path) -> list[str]:
    """Read KEY=VALUE lines into os.environ. Returns the names it set."""
    if not path.exists():
        return []
    names = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            names.append(key)
    return names


def load_dotenv(announce: bool = True) -> list[str]:
    """Load the .env named by SLEEPER_ENV_FILE, or ./.env. Call it first thing.

    Announces on stderr rather than stdout: discover prints a pasteable YAML
    block, and a status line in the middle of it would have to be deleted by
    hand before the config could be saved.
    """
    loaded = load_env_file(Path(os.environ.get(ENV_FILE_VAR, DEFAULT_ENV_FILE)))
    if loaded and announce:
        print(f"loaded {', '.join(sorted(loaded))} from .env", file=sys.stderr)
    return loaded

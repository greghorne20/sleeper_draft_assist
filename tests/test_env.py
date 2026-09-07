"""The .env loader. Every CLI defaults its arguments from the environment, so a
file that loads half-way or overrides a real export would change what a command
runs against without saying so.
"""

from __future__ import annotations

from sleeper_draft.env import load_dotenv, load_env_file


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == []


def test_reads_pairs_and_skips_comments_and_blanks(tmp_path, monkeypatch):
    monkeypatch.delenv("SLEEPER_LEAGUE_ID", raising=False)
    monkeypatch.delenv("SLEEPER_SEASON", raising=False)
    path = tmp_path / ".env"
    path.write_text("# a comment\n\nSLEEPER_LEAGUE_ID=123\nSLEEPER_SEASON = 2026\nnot a pair\n")

    assert sorted(load_env_file(path)) == ["SLEEPER_LEAGUE_ID", "SLEEPER_SEASON"]

    import os
    assert os.environ["SLEEPER_LEAGUE_ID"] == "123"
    assert os.environ["SLEEPER_SEASON"] == "2026"


def test_quotes_are_stripped(tmp_path, monkeypatch):
    monkeypatch.delenv("SLEEPER_USERNAME", raising=False)
    path = tmp_path / ".env"
    path.write_text('SLEEPER_USERNAME="greg"\n')

    load_env_file(path)

    import os
    assert os.environ["SLEEPER_USERNAME"] == "greg"


def test_a_real_export_wins_over_the_file(tmp_path, monkeypatch):
    """Railway sets real env vars and ships no .env; a stale file must not win."""
    monkeypatch.setenv("SLEEPER_LEAGUE_ID", "exported")
    path = tmp_path / ".env"
    path.write_text("SLEEPER_LEAGUE_ID=from_file\n")

    assert load_env_file(path) == []

    import os
    assert os.environ["SLEEPER_LEAGUE_ID"] == "exported"


def test_the_warroom_model_can_come_from_the_file(tmp_path, monkeypatch):
    """runner.parse_args defaults --model from the environment, so the file has
    to be read before the parser is built."""
    monkeypatch.delenv("ANTHROPIC_CHAT_MODEL", raising=False)
    path = tmp_path / ".env"
    path.write_text('ANTHROPIC_CHAT_MODEL="claude-from-file"\n')

    assert load_env_file(path) == ["ANTHROPIC_CHAT_MODEL"]

    import os
    assert os.environ["ANTHROPIC_CHAT_MODEL"] == "claude-from-file"


def test_load_dotenv_honours_the_env_file_override(tmp_path, monkeypatch):
    monkeypatch.delenv("SLEEPER_SLOT", raising=False)
    path = tmp_path / "elsewhere.env"
    path.write_text("SLEEPER_SLOT=12\n")
    monkeypatch.setenv("SLEEPER_ENV_FILE", str(path))

    assert load_dotenv(announce=False) == ["SLEEPER_SLOT"]

    import os
    assert os.environ["SLEEPER_SLOT"] == "12"

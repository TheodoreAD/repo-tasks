"""Fixtures for the unit tier: no subprocesses, no network, no Docker, nothing outside tmp_path.

The whole tier asserts on the exact command string a task builds, so `c` — invoke's `MockContext`
with `run` stubbed — is the one fixture nearly every test wants. A test needing a *specific* run
result (a particular `Result`, or a dict of command → result) builds its own `MockContext` inline
instead; that is the intended split, not an oversight. See contributing/test-tiers.md.
"""

from pathlib import Path

import pytest
from invoke import MockContext


@pytest.fixture(autouse=True)
def isolated_home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake HOME for every unit test, so nothing in this tier can touch the developer's real one.

    `agents.wire_claude_hook` writes an env-cache file under `Path.home()/.cache/claude-code`; run
    against the real home it left one stale file per test per run (~400 measured). Autouse rather
    than opt-in for the same reason `tmp_cwd` exists: the tier's "nothing outside tmp_path"
    contract should be impossible to forget, not something each test remembers. The tier never
    shells out, so patching `os.environ` is enough — no library holds its own env snapshot here."""
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def c() -> MockContext:
    """A MockContext whose `run` accepts any command and reports success, so a task under test
    executes end to end and `c.run.assert_called_once_with(...)` can pin what it built."""
    return MockContext(run=True)


@pytest.fixture
def tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty directory that is also the working directory, yielded as a Path.

    Most task modules resolve their inputs relative to cwd — `projects.py` reads `pyproject.toml`
    and `repo-tasks.toml`, `dist.clean` removes `dist/`, `selfinstall` reads its stamp file — so a
    test that forgets to chdir reads (or writes) this repo's own files instead of a scratch tree.
    Taking this fixture makes that impossible to forget, where `monkeypatch.chdir(tmp_path)` as a
    first line is something you have to remember every time."""
    monkeypatch.chdir(tmp_path)
    return tmp_path

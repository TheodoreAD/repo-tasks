"""Fixtures for the unit tier: no subprocesses, no network, no Docker, nothing outside tmp_path.

The whole tier asserts on the exact command string a task builds, so `c` — invoke's `MockContext`
with `run` stubbed — is the one fixture nearly every test wants. A test needing a *specific* run
result (a particular `Result`, or a dict of command → result) builds its own `MockContext` inline
instead; that is the intended split, not an oversight. See contributing/test-tiers.md.
"""

import tomllib
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from invoke import MockContext
from pytest_socket import disable_socket, enable_socket

from repo_tasks import projects, version


@pytest.fixture(autouse=True)
def no_network() -> Iterator[None]:
    """Make the tier's "no network" promise structural, the way `tmp_cwd` and `isolated_home` make
    "nothing outside tmp_path" structural. Any `socket.socket()` in a unit test raises
    `SocketBlockedError` naming the call, instead of quietly reaching the internet — or quietly
    hanging on a CI runner that cannot.

    Unix sockets stay allowed: they are local IPC, never the coupling this is guarding against, and
    blocking them breaks tooling that talks to a local daemon over one for reasons unrelated to the
    test.

    An autouse fixture, not `--disable-socket` in `pytest.ini`'s addopts. The plugin is shipped in
    the `repo-tasks-quality` manifest, but the restriction deliberately is not: addopts reaches
    every consumer through `configs.pull`, including single-tier repos with a flat `tests/`, and
    this guard is a promise the unit tier makes rather than one the shared config may impose on a
    layout that never made it. Living in a conftest this package does not ship is what keeps it
    opt-in — see contributing/test-tiers.md.
    """
    disable_socket(allow_unix_socket=True)
    yield
    enable_socket()


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


# The version the unit tier asserts against, pinned here rather than read from this repo's own
# `pyproject.toml`. Any value works; this one is what the assertions already used.
PINNED_VERSION = "0.1.0"

# This repo's real version, read once. The fixture below swaps *this* value and nothing else, so a
# test that builds its own project on disk keeps the version it chose.
_REAL_VERSION: str = cast(
    "str", tomllib.loads((Path(__file__).parents[2] / "pyproject.toml").read_text())["project"]["version"]
)


@pytest.fixture(autouse=True)
def pinned_version(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make *this repo's* version a fixture value, so assertions stop depending on a mutable fact.

    Several tests assert version strings derived from the real `pyproject.toml` — a branch named
    `release/0.2.0`, a `--new-version` argument, a tag that must not already exist. Those were
    correct only while the version never moved: bumping `0.1.0` to `0.2.0` made `next_version(...)`
    return `0.3.0` and turned 11 of them red, found 2026-09-04 by cutting this repo's first real
    release. See plans/2026-09-04-release-breaks-the-test-suite.md.

    Autouse, because the failure mode is a test *silently* depending on the repo's own version, and
    an opt-in fixture only protects the tests someone remembered to opt in.

    Scoped to the repo's own version rather than to every resolution, which the first version of this
    fixture got wrong: `set_dev`'s test writes a `pyproject.toml` into `tmp_cwd` and then asserts
    against the version it put there, so blanket-replacing whatever `_resolve_project` returned broke
    it. Everything else about the project is preserved either way — name, path, workspace members.
    """
    real = version._resolve_project

    def pinned(c: object, group: str | None) -> projects.PythonProject:
        project = real(c, group)  # pyright: ignore[reportArgumentType]
        return replace(project, version=PINNED_VERSION) if project.version == _REAL_VERSION else project

    monkeypatch.setattr(version, "_resolve_project", pinned)
    return PINNED_VERSION

"""Tests for repo_tasks.interactive: the one runner that hands a command the real terminal.

The subprocess is doubled — this tier attaches nothing to a terminal — so what is pinned is the
shape: argv split from the command, stdio inherited (nothing captured, nothing piped), the exit code
carried into `Exit`, and the command printed first. Whether a login *completes* on Python 3.14 is
exactly what a mock cannot see, and is `power-user-linux-setup`'s container tier's question."""

import subprocess
from types import SimpleNamespace

import pytest
from invoke import Exit

from repo_tasks import interactive


def _double(monkeypatch, returncode: int = 0) -> list[tuple[list[str], dict[str, object]]]:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_runs_the_command_as_argv_with_the_terminal_attached(monkeypatch):
    calls = _double(monkeypatch)
    interactive.run_interactive("docker login ghcr.io")
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ["docker", "login", "ghcr.io"]
    # Inherited stdio is the whole mechanism: no capture, no pipe, no input, no shell.
    assert not {"stdin", "stdout", "stderr", "input", "capture_output", "shell"} & kwargs.keys()


def test_prints_the_command_before_running_it(monkeypatch, capsys):
    _double(monkeypatch)
    interactive.run_interactive("helm registry login ghcr.io")
    assert capsys.readouterr().out == "helm registry login ghcr.io\n"


def test_a_failing_command_stops_with_its_own_exit_code(monkeypatch):
    _double(monkeypatch, returncode=125)
    with pytest.raises(Exit) as exc_info:
        interactive.run_interactive("docker login ghcr.io")
    assert exc_info.value.code == 125


def test_quoting_survives_the_split(monkeypatch):
    calls = _double(monkeypatch)
    interactive.run_interactive("tool --name 'two words'")
    assert calls[0][0] == ["tool", "--name", "two words"]

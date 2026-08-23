"""Tests for repo_tasks.direnv: allow's idempotent direnv-present/absent branches."""

from invoke import MockContext, Result

from repo_tasks import direnv


def test_allow_runs_direnv_allow_when_present(monkeypatch):
    monkeypatch.setattr(direnv, "_command_exists", lambda name: True)
    c = MockContext(run=True)
    direnv.allow.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("direnv allow", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_allow_skips_when_direnv_missing(monkeypatch, capsys):
    monkeypatch.setattr(direnv, "_command_exists", lambda name: False)
    c = MockContext(run=Result())
    direnv.allow.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_not_called()  # pyright: ignore[reportAttributeAccessIssue]
    assert "direnv not found" in capsys.readouterr().out

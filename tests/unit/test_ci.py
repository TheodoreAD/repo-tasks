"""Tests for repo_tasks.ci: the command `status` builds, plus the real logic — deciding which
conclusion is worth stopping for, and which run's conclusion counts."""

import json

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import ci


def _listing(*runs: dict[str, str]) -> MockContext:
    return MockContext(run=Result(stdout=json.dumps(list(runs)), exited=0))


def _run(conclusion: str | None = "success", status: str = "completed", **extra: str) -> dict[str, str]:
    entry = {
        "status": status,
        "workflowName": "CI",
        "headBranch": "main",
        "createdAt": "2026-08-26T10:00:00Z",
        "url": "https://github.com/o/r/actions/runs/1",
        **extra,
    }
    if conclusion is not None:
        entry["conclusion"] = conclusion
    return entry


def test_status_builds_the_gh_command_with_branch_and_limit():
    c = _listing(_run())
    ci.status.body(c, branch="develop", limit=3)
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        f"gh run list --branch develop --limit 3 --json {ci._FIELDS}",
        echo=True,
        warn=True,
        hide=True,
    )


def test_status_passes_when_the_latest_run_succeeded(capsys):
    ci.status.body(_listing(_run()))
    assert "success" in capsys.readouterr().out


def test_status_stops_when_the_latest_run_failed(capsys):
    with pytest.raises(Exit) as exc_info:
        ci.status.body(_listing(_run(conclusion="failure")))
    assert exc_info.value.code == 1
    assert "most recent main run failed" in str(exc_info.value.message)


def test_status_ignores_an_older_failure(capsys):
    # An older failure that has since been fixed is history, not a reason to block the next push.
    ci.status.body(_listing(_run(), _run(conclusion="failure")))
    assert "failure" in capsys.readouterr().out


def test_status_does_not_stop_on_a_cancelled_run():
    # Usually the concurrency group doing its job when a newer push superseded an older run.
    ci.status.body(_listing(_run(conclusion="cancelled")))


def test_status_tolerates_a_run_still_in_progress(capsys):
    # No conclusion yet — reported by its status rather than treated as unknown-and-failed.
    ci.status.body(_listing(_run(conclusion=None, status="in_progress")))
    assert "in_progress" in capsys.readouterr().out


def test_status_reports_a_repo_with_no_runs(capsys):
    ci.status.body(MockContext(run=Result(stdout="[]", exited=0)))
    assert "no runs recorded" in capsys.readouterr().out


def test_status_surfaces_a_gh_failure_rather_than_parsing_nothing():
    # An unauthenticated gh, or a repo with no remote, must not read as "no runs".
    c = MockContext(run=Result(stdout="", stderr="gh: not authenticated\n", exited=4))
    with pytest.raises(Exit) as exc_info:
        ci.status.body(c)
    assert exc_info.value.code == 4

"""Tests for repo_tasks.ci: the command `status` builds, plus the real logic — deciding which
conclusion is worth stopping for, which run's conclusion counts, and which annotations are worth
printing."""

import json

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import ci


def _listing(*runs: dict[str, object]) -> MockContext:
    return MockContext(run=Result(stdout=json.dumps(list(runs)), exited=0))


def _run(
    conclusion: str | None = "success",
    status: str = "completed",
    run_id: int | None = None,
    **extra: str,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "status": status,
        "workflowName": "CI",
        "headBranch": "main",
        "createdAt": "2026-08-26T10:00:00Z",
        "url": "https://github.com/o/r/actions/runs/1",
        **extra,
    }
    if conclusion is not None:
        entry["conclusion"] = conclusion
    # Absent unless asked for, so the tests that predate annotations keep making exactly one call.
    if run_id is not None:
        entry["databaseId"] = run_id
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


def _annotated(*, jobs: str, annotations: list[dict[str, str]], run_id: int = 7) -> MockContext:
    """A context answering all three calls `status` makes when the run carries a databaseId: the
    run listing, that run's job ids, and each job's annotations. Keyed by command, because a single
    Result would answer the run listing to every one of them."""
    listing = json.dumps([_run(run_id=run_id)])
    return MockContext(
        run={
            f"gh run list --branch main --limit 10 --json {ci._FIELDS}": Result(stdout=listing, exited=0),
            f"gh api repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs --jq '.jobs[].id'": Result(
                stdout=jobs, exited=0
            ),
            "gh api repos/{owner}/{repo}/check-runs/11/annotations": Result(stdout=json.dumps(annotations), exited=0),
            "gh api repos/{owner}/{repo}/check-runs/12/annotations": Result(stdout=json.dumps(annotations), exited=0),
        }
    )


_DEPRECATION = {
    "annotation_level": "warning",
    "message": (
        "Node.js 20 is deprecated. The following actions target Node.js 20 but are being\n"
        "forced to run on Node.js 24: actions/checkout@v4."
    ),
}


def test_status_prints_a_warning_annotation_on_a_green_run(capsys):
    # The whole point: the run passed, and the deprecation is only visible here.
    c = _annotated(jobs="11\n", annotations=[_DEPRECATION])
    ci.status.body(c)
    out = capsys.readouterr().out
    assert "success" in out
    assert "warning: Node.js 20 is deprecated." in out
    # Re-wrapped onto one line, so a multi-line upstream message stays greppable.
    assert "deprecated. The following actions" in out


def test_status_says_a_matrix_deprecation_once(capsys):
    # Every job of a matrix carries the same annotation; five jobs must not mean five lines.
    c = _annotated(jobs="11\n12\n", annotations=[_DEPRECATION])
    ci.status.body(c)
    assert capsys.readouterr().out.count("Node.js 20 is deprecated") == 1


def test_status_ignores_notice_level_annotations(capsys):
    c = _annotated(jobs="11\n", annotations=[{"annotation_level": "notice", "message": "cache restored"}])
    ci.status.body(c)
    assert "cache restored" not in capsys.readouterr().out


def test_status_does_not_stop_on_an_annotation():
    # An annotation is upstream naming a deadline, not a break — reporting only, by design.
    ci.status.body(_annotated(jobs="11\n", annotations=[_DEPRECATION]))


def test_status_skips_annotations_when_the_listing_has_no_run_id(capsys):
    # Nothing to ask about, and no second call worth making.
    c = _listing(_run())
    ci.status.body(c)
    assert "warning" not in capsys.readouterr().out


def test_status_survives_a_token_that_cannot_read_check_runs(capsys):
    # The status report is the task's real job; a missing scope must not turn it into an error.
    listing = json.dumps([_run(run_id=7)])
    c = MockContext(
        run={
            f"gh run list --branch main --limit 10 --json {ci._FIELDS}": Result(stdout=listing, exited=0),
            "gh api repos/{owner}/{repo}/actions/runs/7/jobs --jq '.jobs[].id'": Result(
                stdout="", stderr="HTTP 403", exited=1
            ),
        }
    )
    ci.status.body(c)
    assert "success" in capsys.readouterr().out

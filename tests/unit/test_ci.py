"""Tests for repo_tasks.ci: the commands `status` and `check-actions` build, plus the real logic —
deciding which conclusion is worth stopping for, which run's conclusion counts, which annotations
are worth printing, and when a pinned action counts as behind."""

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


# --- check-actions -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pinned", "latest", "expected"),
    [
        # A bare major is a moving tag: it already resolves to the newest release under it, so it
        # is current however far the patch line has moved. This is the case a naive string or
        # full-tuple comparison gets wrong, and it is the common one.
        ("v7", "v7.0.1", False),
        ("v7.0.1", "v7.0.1", False),
        # A real major behind, at both precisions the family actually writes.
        ("v9.0.0", "v10.0.1", True),
        ("v3", "v4.6.0", True),
        # Fewer digits upstream than in the pin still ranks, rather than falling off the end.
        ("v9.0.0", "v10", True),
        # A zero-major action, which several devcontainer/CI actions are.
        ("v0.3", "v0.4", True),
        ("v0.3", "v0.3.2", False),
        # No version at all on one side: unrankable, and saying so beats guessing.
        ("main", "v7.0.1", None),
        ("v7", "release-2026-08", None),
    ],
)
def test_is_behind_compares_at_the_precision_the_pin_states(pinned, latest, expected):
    assert ci._is_behind(pinned, latest) is expected


def test_uses_reads_every_shape_a_workflow_writes():
    text = """
jobs:
  quality:
    steps:
      - uses: actions/checkout@v7
      - name: Install uv
        uses: "astral-sh/setup-uv@v10.0.1"
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
"""
    uses = ci._uses_in(text, "ci.yml")
    assert [(u.action, u.version) for u in uses] == [
        ("actions/checkout", "v7"),
        ("astral-sh/setup-uv", "v10.0.1"),
        # A SHA says nothing on its own; the version is the comment beside it.
        ("actions/checkout", "v4"),
    ]


def test_uses_reports_a_sha_pin_with_no_version_comment():
    # Its own finding: zizmor's unpinned-uses policy wants the comment, and without it nothing —
    # this task included — can say what the pin actually is.
    uses = ci._uses_in("      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n", "ci.yml")
    assert uses[0].version is None


def test_uses_skips_what_is_nobody_release_to_track():
    text = """
      - uses: ./.github/actions/setup
      - uses: docker://alpine:3.20
      - uses: actions/checkout@v7
"""
    assert [u.action for u in ci._uses_in(text, "ci.yml")] == ["actions/checkout"]


def test_uses_reduces_a_reusable_workflow_to_its_repo():
    uses = ci._uses_in("    uses: octo/org/.github/workflows/release.yml@v2\n", "release.yml")
    assert uses[0].action == "octo/org"


def test_check_actions_noops_cleanly_in_a_repo_with_no_workflows(capsys):
    c = MockContext(run=Result(stdout="", exited=0))
    ci.check_actions.body(c)
    assert "nothing to do" in capsys.readouterr().out


def _workflow_repo(tmp_path, body: str) -> MockContext:
    workflow = tmp_path / "ci.yml"
    workflow.write_text(body)
    return MockContext(
        run={
            f"git ls-files --cached --others --exclude-standard -- '{tmp_path}/*.yml' '{tmp_path}/*.yaml'": Result(
                stdout=f"{workflow}\n", exited=0
            ),
            "gh api repos/astral-sh/setup-uv/releases/latest --jq .tag_name": Result(stdout="v10.0.1\n", exited=0),
            "gh api repos/actions/checkout/releases/latest --jq .tag_name": Result(stdout="v7.0.1\n", exited=0),
        }
    )


def test_check_actions_names_what_is_behind_and_counts_it(tmp_path, capsys):
    c = _workflow_repo(tmp_path, "      - uses: astral-sh/setup-uv@v9.0.0\n      - uses: actions/checkout@v7\n")
    ci.check_actions.body(c, path=str(tmp_path))
    out = capsys.readouterr().out
    assert "astral-sh/setup-uv@v9.0.0  BEHIND — latest v10.0.1" in out
    assert "actions/checkout@v7  current (latest v7.0.1)" in out
    assert "1 of 2 action(s) behind" in out


def test_check_actions_reports_an_action_that_publishes_no_releases(tmp_path, capsys):
    workflow = tmp_path / "ci.yml"
    workflow.write_text("      - uses: some/action@v1\n")
    c = MockContext(
        run={
            f"git ls-files --cached --others --exclude-standard -- '{tmp_path}/*.yml' '{tmp_path}/*.yaml'": Result(
                stdout=f"{workflow}\n", exited=0
            ),
            "gh api repos/some/action/releases/latest --jq .tag_name": Result(stdout="", stderr="HTTP 404", exited=1),
        }
    )
    ci.check_actions.body(c, path=str(tmp_path))
    assert "publishes no releases" in capsys.readouterr().out


def test_check_actions_does_not_stop_on_a_behind_action(tmp_path):
    # Report-only by design: nobody's commit runs this, so a non-zero exit blocks nothing and would
    # only train its reader to ignore it.
    c = _workflow_repo(tmp_path, "      - uses: astral-sh/setup-uv@v9.0.0\n")
    ci.check_actions.body(c, path=str(tmp_path))

"""Tests for repo_tasks.gitflow: asserts the exact git command sequence each task builds via
invoke's MockContext, following test_quality.py's existing style. release_start/hotfix_start now
branch before bumping (nvie's actual order) — the branch name comes from version.next_version's
pure arithmetic on this repo's real pyproject.toml version (same fixture value test_version.py
relies on), not from actually running bump-my-version (MockContext's blanket run=True stub means
it never really runs)."""

import pytest
from invoke import MockContext, Result

from repo_tasks import gitflow

FOR_EACH_REF = "git for-each-ref --format='%(refname:short)' refs/heads/release/*"


def _finish_context(current_branch, open_release_branch=None):
    """MockContext's dict-keyed `run` only stubs exact command matches (unlike `run=True`'s
    blanket stub) — every git command _finish invokes needs its own entry."""
    version_part = current_branch.split("/", 1)[1]
    merge_back = open_release_branch or "develop"
    return MockContext(
        run={
            "git rev-parse --abbrev-ref HEAD": Result(stdout=f"{current_branch}\n", exited=0),
            "git checkout main": Result(exited=0),
            f"git checkout {merge_back}": Result(exited=0),
            f"git merge --no-ff {current_branch}": Result(exited=0),
            f"git branch -d {current_branch}": Result(exited=0),
            f"git tag v{version_part}": Result(exited=0),
            FOR_EACH_REF: Result(stdout=f"{open_release_branch}\n" if open_release_branch else "", exited=0),
            f"git push origin main {merge_back}": Result(exited=0),
            f"git push origin v{version_part}": Result(exited=0),
        }
    )


def test_feature_start():
    c = MockContext(run=True)
    gitflow.feature_start.body(c, name="foo")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git checkout -b feature/foo develop", echo=True
    )


def test_feature_finish():
    c = MockContext(run=True)
    gitflow.feature_finish.body(c, name="foo")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff feature/foo",), {"echo": True}),
        (("git branch -d feature/foo",), {"echo": True}),
    ]


def test_release_start_branches_off_develop_before_bumping():
    c = MockContext(run=True)
    gitflow.release_start.body(c, bump="minor")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    # checkout develop, then branch (unbumped) — nvie's order, the branch must exist before the
    # bump commit does, so an aborted release never leaves a stray bump commit on develop itself.
    assert call_strings[0] == "git checkout develop"
    assert call_strings[1] == "git checkout -b release/0.2.0"
    assert "--config-file" in call_strings[2]  # the underlying version.bump call, tag=False, runs last


def test_hotfix_start_branches_off_main_before_bumping():
    c = MockContext(run=True)
    gitflow.hotfix_start.body(c, bump="patch")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings[0] == "git checkout main"
    assert call_strings[1] == "git checkout -b hotfix/0.1.1"
    assert "--config-file" in call_strings[2]


def test_release_finish_merges_tags_and_deletes():
    c = _finish_context("release/0.2.0")
    gitflow.release_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue] — [0] is the rev-parse query
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff release/0.2.0",), {"echo": True}),
        (("git tag v0.2.0",), {"echo": True}),
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff release/0.2.0",), {"echo": True}),
        (("git branch -d release/0.2.0",), {"echo": True}),
    ]
    # release_finish never checks for another open release branch — nvie's redirect rule is
    # hotfix-only, so the for-each-ref query should never run here.
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert FOR_EACH_REF not in call_strings


def test_release_finish_pushes_when_requested():
    c = _finish_context("release/0.2.0")
    gitflow.release_finish.body(c, push=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push origin main develop",), {"echo": True}),
        (("git push origin v0.2.0",), {"echo": True}),
    ]


def test_hotfix_finish_merges_into_develop_when_no_release_is_open():
    c = _finish_context("hotfix/0.1.1")
    gitflow.hotfix_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git tag v0.1.1",), {"echo": True}),
        ((FOR_EACH_REF,), {"hide": True}),
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git branch -d hotfix/0.1.1",), {"echo": True}),
    ]


def test_hotfix_finish_redirects_into_an_open_release_branch():
    """nvie's documented exception: 'when a release branch currently exists, the hotfix changes
    need to be merged into that release branch, instead of develop' — develop picks up the fix
    later, when the release itself finishes."""
    c = _finish_context("hotfix/0.1.1", open_release_branch="release/0.2.0")
    gitflow.hotfix_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git tag v0.1.1",), {"echo": True}),
        ((FOR_EACH_REF,), {"hide": True}),
        (("git checkout release/0.2.0",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git branch -d hotfix/0.1.1",), {"echo": True}),
    ]


def test_hotfix_finish_pushes_the_redirect_target_not_develop():
    c = _finish_context("hotfix/0.1.1", open_release_branch="release/0.2.0")
    gitflow.hotfix_finish.body(c, push=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push origin main release/0.2.0",), {"echo": True}),
        (("git push origin v0.1.1",), {"echo": True}),
    ]


def test_finish_raises_when_multiple_release_branches_are_open():
    c = MockContext(
        run={
            "git rev-parse --abbrev-ref HEAD": Result(stdout="hotfix/0.1.1\n", exited=0),
            "git checkout main": Result(exited=0),
            "git merge --no-ff hotfix/0.1.1": Result(exited=0),
            "git tag v0.1.1": Result(exited=0),
            FOR_EACH_REF: Result(stdout="release/0.2.0\nrelease/0.3.0\n", exited=0),
        }
    )
    with pytest.raises(ValueError, match="multiple release"):
        gitflow.hotfix_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]


def test_finish_raises_when_not_on_expected_branch_kind():
    c = MockContext(run={"git rev-parse --abbrev-ref HEAD": Result(stdout="main\n", exited=0)})
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]

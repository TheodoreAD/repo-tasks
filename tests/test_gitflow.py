"""Tests for repo_tasks.gitflow: asserts the exact git/gh command sequence each task builds via
invoke's MockContext, following test_quality.py's existing style. PR mode (the default) is
exercised via exact command-string dict stubs since gh pr create's command is fully deterministic
given branch/version; local mode and release_start/hotfix_start still use MockContext's blanket
run=True stub, since their branch name comes from version.next_version's pure arithmetic on this
repo's real pyproject.toml version (same fixture value test_version.py relies on), not from
actually running bump-my-version."""

import pytest
from invoke import MockContext, Result

from repo_tasks import gitflow

FOR_EACH_REF = "git for-each-ref --format='%(refname:short)' refs/heads/release/*"
PR_URL = "https://github.com/example/repo/pull/42"


def _rev_parse(branch):
    return {"git rev-parse --abbrev-ref HEAD": Result(stdout=f"{branch}\n", exited=0)}


def _gh_pr_command(base, head, title, body):
    return f'gh pr create --base {base} --head {head} --title "{title}" --body "{body}"'


def _gh_pr(base, head, title, body):
    return {_gh_pr_command(base, head, title, body): Result(stdout=f"{PR_URL}\n", exited=0)}


def _ok(*commands):
    return {c: Result(exited=0) for c in commands}


# ---------------------------------------------------------------------------
# feature
# ---------------------------------------------------------------------------


def test_feature_start():
    c = MockContext(run=True)
    gitflow.feature_start.body(c, name="foo")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[0] == (("git checkout -b feature/foo develop",), {"echo": True})  # pyright: ignore[reportAttributeAccessIssue]


def test_feature_finish_pr_mode_opens_a_pr_against_develop(capsys):
    c = MockContext(
        run={
            **_ok("git push -u origin feature/foo"),
            **_gh_pr("develop", "feature/foo", "Feature: foo", "Merging feature/foo into develop."),
        }
    )
    gitflow.feature_finish.body(c, name="foo")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push -u origin feature/foo",), {"echo": True}),
        (
            (_gh_pr_command("develop", "feature/foo", "Feature: foo", "Merging feature/foo into develop."),),
            {"echo": True},
        ),
    ]
    out = capsys.readouterr().out
    assert PR_URL in out
    assert "Next steps" in out


def test_feature_finish_local_merges_directly():
    c = MockContext(run=True)
    gitflow.feature_finish.body(c, name="foo", local=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff feature/foo",), {"echo": True}),
        (("git branch -d feature/foo",), {"echo": True}),
    ]


# ---------------------------------------------------------------------------
# release_start / hotfix_start
# ---------------------------------------------------------------------------


def test_release_start_branches_off_develop_before_bumping():
    c = MockContext(run=True)
    gitflow.release_start.body(c, bump="minor")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings[0] == "git checkout develop"
    assert call_strings[1] == "git checkout -b release/0.2.0"
    assert "--config-file" in call_strings[2]


def test_hotfix_start_branches_off_main_before_bumping():
    c = MockContext(run=True)
    gitflow.hotfix_start.body(c, bump="patch")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings[0] == "git checkout main"
    assert call_strings[1] == "git checkout -b hotfix/0.1.1"
    assert "--config-file" in call_strings[2]


# ---------------------------------------------------------------------------
# release_finish / hotfix_finish — PR mode (default)
# ---------------------------------------------------------------------------


def test_release_finish_pr_mode_opens_a_pr_against_main(capsys):
    c = MockContext(
        run={
            **_rev_parse("release/0.2.0"),
            **_ok("git push -u origin release/0.2.0"),
            **_gh_pr("main", "release/0.2.0", "Release 0.2.0", "Merging release/0.2.0 into main."),
        }
    )
    gitflow.release_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push -u origin release/0.2.0",), {"echo": True}),
        (
            (_gh_pr_command("main", "release/0.2.0", "Release 0.2.0", "Merging release/0.2.0 into main."),),
            {"echo": True},
        ),
    ]
    out = capsys.readouterr().out
    assert "inv gitflow.release-finalize" in out


def test_hotfix_finish_pr_mode_opens_a_pr_against_main():
    c = MockContext(
        run={
            **_rev_parse("hotfix/0.1.1"),
            **_ok("git push -u origin hotfix/0.1.1"),
            **_gh_pr("main", "hotfix/0.1.1", "Hotfix 0.1.1", "Merging hotfix/0.1.1 into main."),
        }
    )
    gitflow.hotfix_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push -u origin hotfix/0.1.1",), {"echo": True}),
        (
            (_gh_pr_command("main", "hotfix/0.1.1", "Hotfix 0.1.1", "Merging hotfix/0.1.1 into main."),),
            {"echo": True},
        ),
    ]


def test_finish_pr_mode_raises_when_not_on_expected_branch_kind():
    c = MockContext(run=_rev_parse("main"))
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]


# ---------------------------------------------------------------------------
# release_finish / hotfix_finish — local mode
# ---------------------------------------------------------------------------


def _local_finish_context(current_branch, open_release_branch=None):
    version_part = current_branch.split("/", 1)[1]
    merge_back = open_release_branch or "develop"
    return MockContext(
        run={
            **_rev_parse(current_branch),
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


def test_release_finish_local_merges_tags_and_deletes():
    c = _local_finish_context("release/0.2.0")
    gitflow.release_finish.body(c, local=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff release/0.2.0",), {"echo": True}),
        (("git tag v0.2.0",), {"echo": True}),
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff release/0.2.0",), {"echo": True}),
        (("git branch -d release/0.2.0",), {"echo": True}),
    ]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert FOR_EACH_REF not in call_strings  # release never checks for another open release branch


def test_release_finish_local_pushes_when_requested():
    c = _local_finish_context("release/0.2.0")
    gitflow.release_finish.body(c, local=True, push=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push origin main develop",), {"echo": True}),
        (("git push origin v0.2.0",), {"echo": True}),
    ]


def test_hotfix_finish_local_merges_into_develop_when_no_release_is_open():
    c = _local_finish_context("hotfix/0.1.1")
    gitflow.hotfix_finish.body(c, local=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git tag v0.1.1",), {"echo": True}),
        ((FOR_EACH_REF,), {"hide": True}),
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git branch -d hotfix/0.1.1",), {"echo": True}),
    ]


def test_hotfix_finish_local_redirects_into_an_open_release_branch():
    """nvie's documented exception: 'when a release branch currently exists, the hotfix changes
    need to be merged into that release branch, instead of develop'."""
    c = _local_finish_context("hotfix/0.1.1", open_release_branch="release/0.2.0")
    gitflow.hotfix_finish.body(c, local=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout main",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git tag v0.1.1",), {"echo": True}),
        ((FOR_EACH_REF,), {"hide": True}),
        (("git checkout release/0.2.0",), {"echo": True}),
        (("git merge --no-ff hotfix/0.1.1",), {"echo": True}),
        (("git branch -d hotfix/0.1.1",), {"echo": True}),
    ]


def test_finish_local_raises_when_multiple_release_branches_are_open():
    c = MockContext(
        run={
            **_rev_parse("hotfix/0.1.1"),
            "git checkout main": Result(exited=0),
            "git merge --no-ff hotfix/0.1.1": Result(exited=0),
            "git tag v0.1.1": Result(exited=0),
            FOR_EACH_REF: Result(stdout="release/0.2.0\nrelease/0.3.0\n", exited=0),
        }
    )
    with pytest.raises(ValueError, match="multiple release"):
        gitflow.hotfix_finish.body(c, local=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]


def test_finish_local_raises_when_not_on_expected_branch_kind():
    c = MockContext(run=_rev_parse("main"))
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finish.body(c, local=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]


# ---------------------------------------------------------------------------
# release_finalize / hotfix_finalize
# ---------------------------------------------------------------------------


def _finalize_context(current_branch, tag, open_release_branch=None):
    sync_branch = f"sync/{tag}"
    target = open_release_branch or "develop"
    return MockContext(
        run={
            **_rev_parse(current_branch),
            "git fetch origin main": Result(exited=0),
            "git checkout main": Result(exited=0),
            "git merge --ff-only origin/main": Result(exited=0),
            f"git tag {tag}": Result(exited=0),
            f"git push origin {tag}": Result(exited=0),
            FOR_EACH_REF: Result(stdout=f"{open_release_branch}\n" if open_release_branch else "", exited=0),
            f"git checkout -b {sync_branch}": Result(exited=0),
            **_ok(f"git push -u origin {sync_branch}"),
            **_gh_pr(target, sync_branch, f"Sync {tag} into {target}", f"Merging {tag} (main) into {target}."),
        }
    )


def test_release_finalize_fetches_tags_and_opens_a_develop_pr(capsys):
    c = _finalize_context("release/0.2.0", "v0.2.0")
    gitflow.release_finalize.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings == [
        "git rev-parse --abbrev-ref HEAD",
        "git fetch origin main",
        "git checkout main",
        "git merge --ff-only origin/main",
        "git tag v0.2.0",
        "git push origin v0.2.0",
        "git checkout -b sync/v0.2.0",
        "git push -u origin sync/v0.2.0",
        _gh_pr_command("develop", "sync/v0.2.0", "Sync v0.2.0 into develop", "Merging v0.2.0 (main) into develop."),
    ]
    # release_finalize never checks for another open release branch — the redirect rule is
    # hotfix-only, same as local mode.
    assert FOR_EACH_REF not in call_strings
    out = capsys.readouterr().out
    assert PR_URL in out


def test_hotfix_finalize_targets_develop_when_no_release_is_open():
    c = _finalize_context("hotfix/0.1.1", "v0.1.1")
    gitflow.hotfix_finalize.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert FOR_EACH_REF in call_strings
    assert call_strings[-1].startswith("gh pr create --base develop")


def test_hotfix_finalize_redirects_into_an_open_release_branch():
    c = _finalize_context("hotfix/0.1.1", "v0.1.1", open_release_branch="release/0.2.0")
    gitflow.hotfix_finalize.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings[-1].startswith("gh pr create --base release/0.2.0")


def test_finalize_raises_when_not_on_expected_branch_kind():
    c = MockContext(run=_rev_parse("main"))
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finalize.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]


# ---------------------------------------------------------------------------
# support — start only, no finish/merge-back; matches nvie's own git-flow tool's scope
# ---------------------------------------------------------------------------


def test_support_start_branches_off_the_given_base(capsys):
    c = MockContext(run=True)
    gitflow.support_start.body(c, version="1.4.x", base="v1.4.0")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("git checkout -b support/1.4.x v1.4.0", echo=True)  # pyright: ignore[reportAttributeAccessIssue]
    out = capsys.readouterr().out
    assert "support/1.4.x" in out
    assert "never merges back" in out

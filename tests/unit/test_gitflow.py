"""Tests for repo_tasks.gitflow: asserts the exact git/gh command sequence each task builds via
invoke's MockContext, following test_quality.py's existing style. PR mode (the default) is
exercised via exact command-string dict stubs since gh pr create's command is fully deterministic
given branch/version; local mode and release_start/hotfix_start still use MockContext's blanket
run=True stub, since their branch name comes from version.next_version's pure arithmetic on this
repo's real pyproject.toml version (same fixture value test_version.py relies on), not from
actually running bump-my-version."""

import re

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


def _pr_state_command(branch):
    return f"gh pr view {branch} --json state --jq .state"


def _pr_state(branch: str, state: str | None = "MERGED"):
    """`gh` answers the head branch's PR state; `exited=1` (no `state`) is gh's own "no pull
    requests found" — the shape `_require_merged_pr` sees when *_finish never ran."""
    if state is None:
        return {_pr_state_command(branch): Result(exited=1)}
    return {_pr_state_command(branch): Result(stdout=f"{state}\n", exited=0)}


def _tag_list(tag, exists=False):
    return {f"git tag --list {tag}": Result(stdout=f"{tag}\n" if exists else "", exited=0)}


# ---------------------------------------------------------------------------
# feature
# ---------------------------------------------------------------------------


def test_feature_start(c):
    gitflow.feature_start.body(c, name="foo")
    assert c.run.call_args_list[0] == (("git checkout -b feature/foo develop",), {"echo": True})


def test_feature_finish_pr_mode_opens_a_pr_against_develop(capsys):
    c = MockContext(
        run={
            **_ok("git push -u origin feature/foo"),
            **_gh_pr("develop", "feature/foo", "Feature: foo", "Merging feature/foo into develop."),
        }
    )
    gitflow.feature_finish.body(c, name="foo")
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


def test_feature_finish_local_merges_directly(c):
    gitflow.feature_finish.body(c, name="foo", local=True)
    assert c.run.call_args_list == [
        (("git checkout develop",), {"echo": True}),
        (("git merge --no-ff feature/foo",), {"echo": True}),
        (("git branch -d feature/foo",), {"echo": True}),
    ]


# ---------------------------------------------------------------------------
# release_start / hotfix_start
# ---------------------------------------------------------------------------


def test_release_start_branches_off_develop_before_bumping_to_rc1(c):
    gitflow.release_start.body(c, bump="minor")
    call_strings = [call[0][0] for call in c.run.call_args_list]
    assert call_strings[0] == "git checkout develop"
    assert call_strings[1] == "git tag --list v0.2.0"  # the final version's tag, which is the branch's name
    assert call_strings[2] == "git checkout -b release/0.2.0"
    # rc1 is bump-my-version's own arithmetic for `minor` under the rc scheme — no --new-version.
    assert call_strings[3].startswith("bump-my-version bump minor --config-file ")
    assert "--new-version" not in call_strings[3]


def test_hotfix_start_branches_off_main_and_bumps_straight_to_final(c):
    gitflow.hotfix_start.body(c, bump="patch")
    call_strings = [call[0][0] for call in c.run.call_args_list]
    assert call_strings[0] == "git checkout main"
    assert call_strings[1] == "git tag --list v0.1.1"
    assert call_strings[2] == "git checkout -b hotfix/0.1.1"
    assert call_strings[3].startswith("bump-my-version bump patch --config-file ")
    assert call_strings[3].endswith(" --new-version 0.1.1")


def test_hotfix_start_rc_opts_into_the_candidate_cycle(c, capsys):
    gitflow.hotfix_start.body(c, bump="patch", rc=True)
    call_strings = [call[0][0] for call in c.run.call_args_list]
    assert call_strings[2] == "git checkout -b hotfix/0.1.1"  # still named after the final
    assert "--new-version" not in call_strings[3]
    assert "release-candidate" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# release_candidate — rcN -> rcN+1, tagged and pushed on the branch itself
# ---------------------------------------------------------------------------


def _candidate_context(branch, current, next_tag):
    return MockContext(
        run={
            **_rev_parse(branch),
            **_tag_list(next_tag),
            **_ok(f"git push origin {branch} {next_tag}"),
        }
    )


def test_release_candidate_bumps_rc_tags_and_pushes(monkeypatch, capsys):
    c = _candidate_context("release/0.2.0", "0.2.0rc1", "v0.2.0rc2")
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.2.0rc1")
    bumps = []
    monkeypatch.setattr(
        gitflow, "version_bump", lambda c, part, group=None, tag=True, rc=True: bumps.append((part, tag))
    )
    gitflow.release_candidate.body(c)
    assert bumps == [("rc", True)]
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings == [
        "git rev-parse --abbrev-ref HEAD",
        "git tag --list v0.2.0rc2",
        "git push origin release/0.2.0 v0.2.0rc2",
    ]
    out = capsys.readouterr().out
    assert "v0.2.0rc2 pushed" in out
    assert "inv gitflow.release-finish" in out


def test_release_candidate_works_on_a_hotfix_branch_that_opted_in(monkeypatch, capsys):
    c = _candidate_context("hotfix/0.1.1", "0.1.1rc1", "v0.1.1rc2")
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.1.1rc1")
    monkeypatch.setattr(gitflow, "version_bump", lambda c, part, group=None, tag=True, rc=True: None)
    gitflow.release_candidate.body(c)
    assert "inv gitflow.hotfix-finish" in capsys.readouterr().out


def test_release_candidate_refuses_off_a_release_or_hotfix_branch():
    c = MockContext(run=_rev_parse("develop"))
    with pytest.raises(ValueError, match="release/\\* or hotfix/\\*"):
        gitflow.release_candidate.body(c)


def test_release_candidate_refuses_when_the_next_rc_tag_exists(monkeypatch):
    c = MockContext(run={**_rev_parse("release/0.2.0"), **_tag_list("v0.2.0rc2", exists=True)})
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.2.0rc1")
    with pytest.raises(ValueError, match=re.escape("v0.2.0rc2 already exists")):
        gitflow.release_candidate.body(c)


def test_release_candidate_refuses_a_final_version(monkeypatch):
    # A hotfix that went straight to final has no candidate to advance.
    c = MockContext(run=_rev_parse("hotfix/0.1.1"))
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.1.1")
    with pytest.raises(ValueError, match="final version"):
        gitflow.release_candidate.body(c)


def test_start_raises_before_branching_when_the_versions_tag_already_exists():
    """develop still carrying the pre-release version — a sync/<tag> PR closed unmerged — makes
    the arithmetic land on a version main already shipped. Refused before any branch is cut."""
    c = MockContext(run={**_ok("git checkout develop"), **_tag_list("v0.2.0", exists=True)})
    with pytest.raises(ValueError, match=re.escape("v0.2.0 already exists")):
        gitflow.release_start.body(c, bump="minor")
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert not any(s.startswith("git checkout -b") for s in call_strings)


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
    gitflow.release_finish.body(c)
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
    gitflow.hotfix_finish.body(c)
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
        gitflow.release_finish.body(c)


def test_release_finish_drops_the_rc_before_opening_the_pr(monkeypatch):
    """The version main receives is the final one the branch was named after — one more bump
    commit on the branch, before the push that makes the PR."""
    c = MockContext(
        run={
            **_rev_parse("release/0.2.0"),
            **_ok("git push -u origin release/0.2.0"),
            **_gh_pr("main", "release/0.2.0", "Release 0.2.0", "Merging release/0.2.0 into main."),
        }
    )
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.2.0rc3")
    events = []
    monkeypatch.setattr(
        gitflow, "version_bump", lambda c, part, group=None, tag=True, rc=True: events.append(("bump", part, tag))
    )
    gitflow.release_finish.body(c)
    assert events == [("bump", "final", False)]


def test_release_finish_local_drops_the_rc_before_merging(monkeypatch):
    c = _local_finish_context("release/0.2.0")
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.2.0rc1")
    bumps = []
    monkeypatch.setattr(gitflow, "version_bump", lambda c, part, group=None, tag=True, rc=True: bumps.append(part))
    gitflow.release_finish.body(c, local=True)
    assert bumps == ["final"]
    assert c.run.call_args_list[1][0][0] == "git checkout main"  # pyright: ignore[reportAttributeAccessIssue]


def test_hotfix_finish_has_nothing_to_drop_without_an_rc(monkeypatch):
    c = _local_finish_context("hotfix/0.1.1")
    monkeypatch.setattr(gitflow, "current_version", lambda c, group=None: "0.1.1")
    bumps = []
    monkeypatch.setattr(gitflow, "version_bump", lambda c, part, group=None, tag=True, rc=True: bumps.append(part))
    gitflow.hotfix_finish.body(c, local=True)
    assert bumps == []


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
    gitflow.release_finish.body(c, local=True)
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
    gitflow.release_finish.body(c, local=True, push=True)
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push origin main develop",), {"echo": True}),
        (("git push origin v0.2.0",), {"echo": True}),
    ]


def test_hotfix_finish_local_merges_into_develop_when_no_release_is_open():
    c = _local_finish_context("hotfix/0.1.1")
    gitflow.hotfix_finish.body(c, local=True)
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
    gitflow.hotfix_finish.body(c, local=True)
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
        gitflow.hotfix_finish.body(c, local=True)


def test_finish_local_raises_when_not_on_expected_branch_kind():
    c = MockContext(run=_rev_parse("main"))
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finish.body(c, local=True)


# ---------------------------------------------------------------------------
# release_finalize / hotfix_finalize
# ---------------------------------------------------------------------------


def _finalize_context(current_branch, tag, open_release_branch=None):
    sync_branch = f"sync/{tag}"
    target = open_release_branch or "develop"
    return MockContext(
        run={
            **_rev_parse(current_branch),
            **_pr_state(current_branch),
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
    gitflow.release_finalize.body(c)
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings == [
        "git rev-parse --abbrev-ref HEAD",
        _pr_state_command("release/0.2.0"),
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
    gitflow.hotfix_finalize.body(c)
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert FOR_EACH_REF in call_strings
    assert call_strings[-1].startswith("gh pr create --base develop")


def test_hotfix_finalize_redirects_into_an_open_release_branch():
    c = _finalize_context("hotfix/0.1.1", "v0.1.1", open_release_branch="release/0.2.0")
    gitflow.hotfix_finalize.body(c)
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings[-1].startswith("gh pr create --base release/0.2.0")


def test_finalize_raises_when_not_on_expected_branch_kind():
    c = MockContext(run=_rev_parse("main"))
    with pytest.raises(ValueError, match="release/"):
        gitflow.release_finalize.body(c)


@pytest.mark.parametrize("state", ["OPEN", "CLOSED", None])
def test_finalize_refuses_an_unmerged_pr_before_touching_main(state):
    """`git merge --ff-only origin/main` succeeds trivially when nothing merged, so without this
    guard the tag would land on the old tip and be pushed — the wrong-commit tag state."""
    c = MockContext(run={**_rev_parse("release/0.2.0"), **_pr_state("release/0.2.0", state)})
    with pytest.raises(ValueError, match="not merged yet"):
        gitflow.release_finalize.body(c)
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert not any(s.startswith("git ") and s != "git rev-parse --abbrev-ref HEAD" for s in call_strings)


# ---------------------------------------------------------------------------
# support_start — start only, no finish/merge-back; matches nvie's own git-flow tool's scope
# ---------------------------------------------------------------------------


def test_support_start_branches_off_the_given_base(c, capsys):
    gitflow.support_start.body(c, version="1.4.x", base="v1.4.0")
    c.run.assert_called_once_with("git checkout -b support/1.4.x v1.4.0", echo=True)
    out = capsys.readouterr().out
    assert "support/1.4.x" in out
    assert "never merges back" in out
    assert "support-hotfix-start" in out  # points at the actual patch flow, not "commit directly"


# ---------------------------------------------------------------------------
# support_hotfix — a hotfix-shaped flow targeting a support/* branch instead of main. support/* is
# protected exactly like main (it ships to prod too), so patching it needs the same PR discipline —
# but never touches develop or the release-branch redirect rule, since a support line is already
# permanently diverged from the mainline.
# ---------------------------------------------------------------------------


def test_support_hotfix_start_branches_off_the_support_branch_before_bumping(c):
    gitflow.support_hotfix_start.body(c, support="1.4.x", bump="patch")
    call_strings = [call[0][0] for call in c.run.call_args_list]
    assert call_strings[0] == "git checkout support/1.4.x"
    assert call_strings[1] == "git tag --list v0.1.1"
    assert call_strings[2] == "git checkout -b support-hotfix/1.4.x/0.1.1"
    assert "--config-file" in call_strings[3]


def test_support_hotfix_finish_pr_mode_opens_a_pr_against_the_support_branch(capsys):
    c = MockContext(
        run={
            **_rev_parse("support-hotfix/1.4.x/0.1.1"),
            **_ok("git push -u origin support-hotfix/1.4.x/0.1.1"),
            **_gh_pr(
                "support/1.4.x",
                "support-hotfix/1.4.x/0.1.1",
                "Support patch v0.1.1",
                "Merging support-hotfix/1.4.x/0.1.1 into support/1.4.x.",
            ),
        }
    )
    gitflow.support_hotfix_finish.body(c, support="1.4.x")
    out = capsys.readouterr().out
    assert "inv gitflow.support-hotfix-finalize --support=1.4.x" in out


def test_support_hotfix_finish_local_merges_tags_and_deletes():
    branch = "support-hotfix/1.4.x/0.1.1"
    c = MockContext(
        run={
            **_rev_parse(branch),
            "git checkout support/1.4.x": Result(exited=0),
            f"git merge --no-ff {branch}": Result(exited=0),
            "git tag v0.1.1": Result(exited=0),
            f"git branch -d {branch}": Result(exited=0),
        }
    )
    gitflow.support_hotfix_finish.body(c, support="1.4.x", local=True)
    assert c.run.call_args_list[1:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git checkout support/1.4.x",), {"echo": True}),
        ((f"git merge --no-ff {branch}",), {"echo": True}),
        (("git tag v0.1.1",), {"echo": True}),
        ((f"git branch -d {branch}",), {"echo": True}),
    ]


def test_support_hotfix_finish_local_pushes_when_requested():
    branch = "support-hotfix/1.4.x/0.1.1"
    c = MockContext(
        run={
            **_rev_parse(branch),
            "git checkout support/1.4.x": Result(exited=0),
            f"git merge --no-ff {branch}": Result(exited=0),
            "git tag v0.1.1": Result(exited=0),
            f"git branch -d {branch}": Result(exited=0),
            **_ok("git push origin support/1.4.x", "git push origin v0.1.1"),
        }
    )
    gitflow.support_hotfix_finish.body(c, support="1.4.x", local=True, push=True)
    assert c.run.call_args_list[-2:] == [  # pyright: ignore[reportAttributeAccessIssue]
        (("git push origin support/1.4.x",), {"echo": True}),
        (("git push origin v0.1.1",), {"echo": True}),
    ]


def test_support_hotfix_finalize_tags_the_support_branch_with_no_second_pr():
    c = MockContext(
        run={
            **_rev_parse("support-hotfix/1.4.x/0.1.1"),
            **_pr_state("support-hotfix/1.4.x/0.1.1"),
            "git fetch origin support/1.4.x": Result(exited=0),
            "git checkout support/1.4.x": Result(exited=0),
            "git merge --ff-only origin/support/1.4.x": Result(exited=0),
            "git tag v0.1.1": Result(exited=0),
            **_ok("git push origin v0.1.1"),
        }
    )
    gitflow.support_hotfix_finalize.body(c, support="1.4.x")
    call_strings = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert call_strings == [
        "git rev-parse --abbrev-ref HEAD",
        _pr_state_command("support-hotfix/1.4.x/0.1.1"),
        "git fetch origin support/1.4.x",
        "git checkout support/1.4.x",
        "git merge --ff-only origin/support/1.4.x",
        "git tag v0.1.1",
        "git push origin v0.1.1",
    ]
    assert not any(s.startswith("gh pr create") for s in call_strings)  # never carries into develop


def test_support_hotfix_raises_when_not_on_the_matching_support_hotfix_branch():
    c = MockContext(run=_rev_parse("main"))
    with pytest.raises(ValueError, match=re.escape("support-hotfix/1.4.x/")):
        gitflow.support_hotfix_finish.body(c, support="1.4.x")


def test_support_hotfix_raises_for_a_different_support_lines_branch():
    """On support-hotfix/1.5.x/0.1.1 but finishing for support 1.4.x — must not accept it."""
    c = MockContext(run=_rev_parse("support-hotfix/1.5.x/0.1.1"))
    with pytest.raises(ValueError, match=re.escape("support-hotfix/1.4.x/")):
        gitflow.support_hotfix_finish.body(c, support="1.4.x")


def test_hotfix_start_branches_off_the_configured_trunk(c, monkeypatch):
    """The finding the setting exists for. On a repo whose trunk is `master` this task used to run
    `git checkout main` — a ref that does not exist there — with no flag to override, which made the
    whole gitflow module unusable rather than merely awkward.

    The resolver is stubbed rather than driven from a real `repo-tasks.toml`: reading one needs a
    `tmp_cwd`, and these version-dependent tasks resolve their branch name from *this* repo's real
    pyproject.toml (see the module docstring), so moving cwd takes the version away with it.
    `test_projects.py` owns whether the file parses; this owns whether gitflow asks."""
    monkeypatch.setattr(gitflow, "trunk_branch", lambda: "master")
    gitflow.hotfix_start.body(c, bump="patch")
    assert c.run.call_args_list[0] == (("git checkout master",), {"echo": True})


def test_feature_start_branches_off_the_configured_development_branch(c, monkeypatch):
    monkeypatch.setattr(gitflow, "develop_branch", lambda: "integration")
    gitflow.feature_start.body(c, name="foo")
    assert c.run.call_args_list[0] == (("git checkout -b feature/foo integration",), {"echo": True})

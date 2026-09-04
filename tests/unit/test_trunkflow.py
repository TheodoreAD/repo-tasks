"""Tests for repo_tasks.trunkflow: asserts the exact git command sequence `cut` builds via invoke's
MockContext, following test_gitflow.py's style. The version arithmetic comes from
version.next_version's pure function over this repo's real pyproject.toml version, the same fixture
value test_version.py and test_gitflow.py rely on — bump-my-version is never actually run."""

import re

import pytest
from invoke import MockContext, Result

from repo_tasks import trunkflow

BRANCH = "git rev-parse --abbrev-ref HEAD"
STATUS = "git status --porcelain"
FETCH = "git fetch --quiet origin"
# A *compiled* pattern, not a string: MockContext regex-matches a key only when it has a
# `.match` attribute, so a plain string key is only ever compared literally — and the bump's
# `--config-file` is a NamedTemporaryFile whose path differs every run.
BUMP = re.compile(r"bump-my-version bump .*")


def _counts(behind="0", ahead="0", branch="main"):
    return {
        f"git rev-list --count {branch}..origin/{branch}": Result(stdout=f"{behind}\n", exited=0),
        f"git rev-list --count origin/{branch}..{branch}": Result(stdout=f"{ahead}\n", exited=0),
    }


def _ctx(*, branch="main", dirty=False, behind="0", ahead="0"):
    return MockContext(
        run={
            BRANCH: Result(stdout=f"{branch}\n", exited=0),
            STATUS: Result(stdout=" M src/x.py\n" if dirty else "", exited=0),
            FETCH: Result(exited=0),
            **_counts(behind=behind, ahead=ahead),
            BUMP: Result(exited=0),
            **{cmd: Result(exited=0) for cmd in ("git push origin main", "git push origin v0.2.0", "uv lock --check")},
        },
        repeat=True,
    )


def test_cut_bumps_tags_and_pushes_both():
    c = _ctx()
    trunkflow.cut.body(c)
    calls = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    bump = next(cmd for cmd in calls if cmd.startswith("bump-my-version"))
    # Straight to a final version: no rc in the target, and no --new-version needed for a plain minor.
    assert bump.startswith("bump-my-version bump minor --config-file ")
    assert "rc" not in bump
    assert calls[-2:] == ["git push origin main", "git push origin v0.2.0"]


def test_cut_refuses_when_not_on_the_trunk():
    c = _ctx(branch="feature/x")
    with pytest.raises(ValueError, match="on feature/x, not main"):
        trunkflow.cut.body(c)


def test_cut_refuses_a_dirty_tree():
    """A bump commits every file the version appears in, so anything else modified would ride along."""
    c = _ctx(dirty=True)
    with pytest.raises(ValueError, match="working tree is not clean"):
        trunkflow.cut.body(c)


def test_cut_refuses_when_behind_the_remote():
    c = _ctx(behind="3")
    with pytest.raises(ValueError, match=r"3 commit\(s\) behind"):
        trunkflow.cut.body(c)


def test_cut_proceeds_when_ahead_of_the_remote():
    """Being ahead is the normal case — those commits are what the release contains."""
    c = _ctx(ahead="2")
    trunkflow.cut.body(c)
    assert "git push origin main" in [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]


def test_cut_takes_a_named_branch():
    c = MockContext(
        run={
            BRANCH: Result(stdout="trunk\n", exited=0),
            STATUS: Result(stdout="", exited=0),
            FETCH: Result(exited=0),
            **_counts(branch="trunk"),
            BUMP: Result(exited=0),
            "git push origin trunk": Result(exited=0),
            "git push origin v0.2.0": Result(exited=0),
            "uv lock --check": Result(exited=0),
        },
        repeat=True,
    )
    trunkflow.cut.body(c, branch="trunk")
    assert "git push origin trunk" in [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]

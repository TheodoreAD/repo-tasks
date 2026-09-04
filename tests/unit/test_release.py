"""Tests for repo_tasks.release: asserts the exact git/gh command each task builds via invoke's
MockContext, following test_gitflow.py's style. Every guard is exercised for its refusal as well as
its pass, since the guards are most of what this module is."""

import pytest
from invoke import MockContext, Result

from repo_tasks import release

TAG = "v0.2.0"

DESCRIBE = "git describe --tags --abbrev=0"
LOCAL = f"git rev-parse --verify --quiet refs/tags/{TAG}"
REMOTE = f"git ls-remote --exit-code --tags origin refs/tags/{TAG}"
VIEW = f"gh release view {TAG}"


def _ctx(*, describe=TAG, local=0, remote=0, view=1):
    """A context whose four probe commands each report what this test wants them to.

    `view` defaults to 1 — no existing Release — because that is the state every successful publish
    starts from, and a test asserting the happy path should not have to say so.
    """
    return MockContext(
        run={
            DESCRIBE: Result(stdout=f"{describe}\n", exited=0 if describe else 128),
            LOCAL: Result(exited=local),
            REMOTE: Result(exited=remote),
            VIEW: Result(exited=view),
            f"gh release create {TAG} --title {TAG} --generate-notes": Result(exited=0),
            f'gh release create {TAG} --title {TAG} --notes "hand written"': Result(exited=0),
            f"gh release create {TAG} --title {TAG} --generate-notes --draft": Result(exited=0),
        }
    )


def test_create_defaults_to_the_latest_tag_and_generates_notes():
    c = _ctx()
    release.create.body(c)
    assert c.run.call_args_list[-1][0][0] == f"gh release create {TAG} --title {TAG} --generate-notes"  # pyright: ignore[reportAttributeAccessIssue]


def test_create_takes_an_explicit_tag_without_asking_git_for_one():
    c = _ctx()
    release.create.body(c, tag=TAG)
    assert DESCRIBE not in [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]


def test_create_uses_explicit_notes_when_given():
    c = _ctx()
    release.create.body(c, tag=TAG, notes="hand written")
    assert c.run.call_args_list[-1][0][0] == f'gh release create {TAG} --title {TAG} --notes "hand written"'  # pyright: ignore[reportAttributeAccessIssue]


def test_create_passes_draft_through():
    c = _ctx()
    release.create.body(c, tag=TAG, draft=True)
    assert c.run.call_args_list[-1][0][0].endswith("--generate-notes --draft")  # pyright: ignore[reportAttributeAccessIssue]


def test_create_refuses_when_the_repo_has_no_tags():
    c = _ctx(describe="")
    with pytest.raises(ValueError, match="no tags in this repository"):
        release.create.body(c)


def test_create_refuses_a_tag_that_does_not_exist_locally():
    c = _ctx(local=1)
    with pytest.raises(ValueError, match="does not exist locally"):
        release.create.body(c, tag=TAG)


def test_create_refuses_a_tag_the_remote_does_not_have():
    """The guard that matters most: `gh release create` would otherwise create the tag itself,
    against whatever the default branch's tip happens to be."""
    c = _ctx(remote=2)
    with pytest.raises(ValueError, match="exists locally but not on origin"):
        release.create.body(c, tag=TAG)


def test_create_refuses_to_publish_over_an_existing_release():
    c = _ctx(view=0)
    with pytest.raises(ValueError, match="already exists"):
        release.create.body(c, tag=TAG)


CONTAINS = f"git branch --contains refs/tags/{TAG} --format='%(refname:short)'"


def _push_ctx(*, local=0, on_remote=1, contains="main"):
    """`on_remote` defaults to 1 — absent — because that is the state a push starts from."""
    return MockContext(
        run={
            DESCRIBE: Result(stdout=f"{TAG}\n", exited=0),
            LOCAL: Result(exited=local),
            REMOTE: Result(exited=on_remote),
            CONTAINS: Result(stdout=f"{contains}\n", exited=0),
            "git push origin main": Result(exited=0),
            f"git push origin {TAG}": Result(exited=0),
        }
    )


def test_push_tag_sends_the_branch_before_the_tag():
    """The branch first, so the tagged commit arrives under a ref rather than reachable only
    from a tag."""
    c = _push_ctx()
    release.push_tag.body(c)
    calls = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert calls[-2:] == ["git push origin main", f"git push origin {TAG}"]


def test_push_tag_is_a_no_op_when_the_tag_is_already_published():
    c = _push_ctx(on_remote=0)
    release.push_tag.body(c)
    calls = [call[0][0] for call in c.run.call_args_list]  # pyright: ignore[reportAttributeAccessIssue]
    assert not [cmd for cmd in calls if cmd.startswith("git push")]


def test_push_tag_refuses_a_tag_that_does_not_exist_locally():
    c = _push_ctx(local=1)
    with pytest.raises(ValueError, match="does not exist locally"):
        release.push_tag.body(c)


def test_push_tag_refuses_a_tag_pointing_off_the_branch():
    """A tag left on an abandoned branch is pushable as though it were the release."""
    c = _push_ctx(contains="feature/x")
    with pytest.raises(ValueError, match="does not point at a commit on main"):
        release.push_tag.body(c)

"""Trunk-based releasing: bump on the trunk, tag it, push. No release branch, no `develop`.

The sibling of `gitflow.py`, and the `-flow` suffix is the class marker — both modules implement a
git branching model, and a third (`githubflow`, `gitlabflow`) would join them by the same naming.
Which one a repo uses is a property of the repo, so the two never both apply; nothing here is a mode
of `gitflow`, and `inv --list` advertising twelve gitflow tasks in a repo with no `develop` is
exactly what having a second namespace avoids.

One task, because that is genuinely all this model is. Where gitflow spends a branch, a PR and an rc
cycle stabilising a release, trunk-based development ships whatever is on the trunk once it is
green — so `cut` bumps and tags, locally, and stops. Both publishing steps live in `release.py` and
are deliberate acts of their own: `release.push-tag` sends the tag, `release.create` turns it into a
GitHub Release. See that module for why they are not here.

No rc cycle here by construction. A release candidate needs somewhere to live while it stabilises,
and the whole point of this model is that there is no such place — a repo that wants one wants
gitflow.
"""

from invoke import Context, task

from .projects import trunk_branch
from .requirements import NETWORK, requires

# `_bump` is the plain function behind the `bump` task; the underscore keeps it out of the CLI
# namespace, not out of sibling modules. Same import shape as gitflow.py's.
from .version import _bump as version_bump  # pyright: ignore[reportPrivateUsage]
from .version import current_version, next_version


def _current_branch(c: Context) -> str:
    return c.run("git rev-parse --abbrev-ref HEAD", hide=True).stdout.strip()


def _require_clean_tree(c: Context):
    """A bump commits every file the version appears in, so an unrelated staged or modified file
    would ride along in the release commit under a message describing only the bump."""
    if c.run("git status --porcelain", hide=True).stdout.strip():
        raise ValueError("working tree is not clean — commit or stash before cutting a release")


def _require_in_sync(c: Context, branch: str):
    """Refuse to tag a trunk that is behind its remote.

    The tag would name a commit that is not what the remote calls the release, and unlike a
    misnamed branch that cannot be cleanly undone once anything has fetched it.
    """
    c.run("git fetch --quiet origin", echo=True)
    behind = c.run(f"git rev-list --count {branch}..origin/{branch}", hide=True).stdout.strip()
    if behind != "0":
        raise ValueError(f"{branch} is {behind} commit(s) behind origin/{branch} — pull before cutting a release")
    ahead = c.run(f"git rev-list --count origin/{branch}..{branch}", hide=True).stdout.strip()
    if ahead != "0":
        print(f"[trunkflow.cut] {branch} is {ahead} commit(s) ahead of origin — they ship in this release")


@requires(NETWORK)
@task(
    help={
        "bump": "Version part to bump: major, minor or patch",
        "branch": "The trunk to release from (default: this repo's trunk)",
        "group": "Version group to bump (default: the repo's own root project)",
        "push": "Push the branch and tag as well. Off by default -- see the docstring",
    }
)
def cut(c: Context, bump: str = "minor", branch: str | None = None, group: str | None = None, push: bool = False):
    """Bump the version on the trunk and tag it, locally.

    Straight to a final version — no release candidate, since this model has no branch to stabilise
    one on.

    **Nothing is pushed unless you ask.** Across this ecosystem the tag push *is* the release gate:
    requests, flask and httpx all publish on a tag push, and PyPA's own guide tells you to push a
    tagged commit to publish. So a bump that pushed its own tag would make publication a side effect
    of asking for a version number. `--push` opts in; `inv release.push-tag` is the same act as its
    own deliberate step, and is what the next-steps output points at.

    Which part to bump follows this repo's surface rule rather than SemVer's breakage rule — minor
    when anything a consumer inherits changed, patch when it did not. See
    contributing/release-flow.md.
    """
    branch = branch or trunk_branch()
    current = _current_branch(c)
    if current != branch:
        raise ValueError(f"on {current}, not {branch} — check out {branch} first, or pass --branch")
    _require_clean_tree(c)
    _require_in_sync(c, branch)

    version = next_version(current_version(c, group), bump, rc=False)
    print(f"[trunkflow.cut] {current_version(c, group)} -> {version}")
    _ = version_bump(c, bump, group=group, tag=True, rc=False)

    if push:
        c.run(f"git push origin {branch}", echo=True)
        c.run(f"git push origin v{version}", echo=True)
        print("\nNext steps:")
        print(f"  - inv release.create --tag v{version}   # publish as a GitHub Release, if wanted")
        return

    print("\nNothing pushed. Next steps:")
    print(f"  - inv release.push-tag --tag v{version}   # publish the tag: this is the release gate")
    print(f"  - inv release.create --tag v{version}     # then a GitHub Release, if wanted")

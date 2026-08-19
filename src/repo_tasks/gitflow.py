"""Raw git plumbing implementing nvie's gitflow branch-naming and merge-back conventions — no
external git-flow binary dependency, every step is a plain c.run("git ...", echo=True).

feature/* branches off develop and merges back to develop only. release/* branches off develop;
hotfix/* branches off main. Both finish by merging into both main and develop, with the release
tag created on main at finish time — not by version.bump at start time, since the branch needs to
exist and be reviewable before the tag is set in stone."""

from invoke import task

from .version import _bump as version_bump


def _current_branch(c):
    return c.run("git rev-parse --abbrev-ref HEAD", hide=True).stdout.strip()


@task
def feature_start(c, name):
    """Branch feature/<name> off develop."""
    c.run(f"git checkout -b feature/{name} develop", echo=True)


@task
def feature_finish(c, name):
    """Merge feature/<name> back into develop and delete it."""
    c.run("git checkout develop", echo=True)
    c.run(f"git merge --no-ff feature/{name}", echo=True)
    c.run(f"git branch -d feature/{name}", echo=True)


def _start(c, kind, base, bump, group):
    c.run(f"git checkout {base}", echo=True)
    new_version = version_bump(c, bump, group=group, tag=False)
    branch = f"{kind}/{new_version}"
    c.run(f"git checkout -b {branch}", echo=True)


@task
def release_start(c, bump, group=None):
    """Bump the version on develop (no tag yet), then branch release/<version> off it."""
    _start(c, "release", "develop", bump, group)


@task
def hotfix_start(c, bump, group=None):
    """Bump the version on main (no tag yet), then branch hotfix/<version> off it."""
    _start(c, "hotfix", "main", bump, group)


def _finish(c, kind, push):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(f"not on a {prefix}* branch (currently on {branch!r})")
    tag = f"v{branch.removeprefix(prefix)}"

    c.run("git checkout main", echo=True)
    c.run(f"git merge --no-ff {branch}", echo=True)
    c.run(f"git tag {tag}", echo=True)
    c.run("git checkout develop", echo=True)
    c.run(f"git merge --no-ff {branch}", echo=True)
    c.run(f"git branch -d {branch}", echo=True)

    if push:
        c.run("git push origin main develop", echo=True)
        c.run(f"git push origin {tag}", echo=True)


@task
def release_finish(c, push=False):
    """Merge the current release/* branch into main (tagged) and develop, then delete it."""
    _finish(c, "release", push)


@task
def hotfix_finish(c, push=False):
    """Merge the current hotfix/* branch into main (tagged) and develop, then delete it."""
    _finish(c, "hotfix", push)

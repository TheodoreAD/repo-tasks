"""Raw git plumbing implementing nvie's gitflow branch-naming and merge-back conventions — no
external git-flow binary dependency, every step is a plain c.run("git ...", echo=True).

feature/* branches off develop and merges back to develop only. release/* branches off develop;
hotfix/* branches off main. Both are cut *before* the version is bumped (nvie's actual order: the
branch exists first, unbumped, and the bump commit lands on the branch itself), and both finish by
merging into main (tagged there) and, ordinarily, develop.

One documented exception, straight from the source article: if a release/* branch is already open
when a hotfix finishes, the hotfix merges into *that* release branch instead of develop directly —
develop picks up the fix later when the release itself finishes, avoiding a bugfix clashing with
an in-flight release's own version bump."""

from invoke import task

from .version import _bump as version_bump
from .version import current_version, next_version


def _current_branch(c):
    return c.run("git rev-parse --abbrev-ref HEAD", hide=True).stdout.strip()


def _open_release_branch(c):
    names = c.run("git for-each-ref --format='%(refname:short)' refs/heads/release/*", hide=True).stdout.split()
    if len(names) > 1:
        raise ValueError(f"multiple release/* branches exist ({names!r}); resolve manually")
    return names[0] if names else None


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
    branch = f"{kind}/{next_version(current_version(c, group=group), bump)}"
    c.run(f"git checkout -b {branch}", echo=True)
    version_bump(c, bump, group=group, tag=False)


@task
def release_start(c, bump, group=None):
    """Branch release/<version> off develop, then bump the version on the release branch (no tag
    yet)."""
    _start(c, "release", "develop", bump, group)


@task
def hotfix_start(c, bump, group=None):
    """Branch hotfix/<version> off main, then bump the version on the hotfix branch (no tag
    yet)."""
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

    merge_back = "develop"
    if kind == "hotfix":
        release_branch = _open_release_branch(c)
        if release_branch is not None:
            merge_back = release_branch

    c.run(f"git checkout {merge_back}", echo=True)
    c.run(f"git merge --no-ff {branch}", echo=True)
    c.run(f"git branch -d {branch}", echo=True)

    if push:
        c.run(f"git push origin main {merge_back}", echo=True)
        c.run(f"git push origin {tag}", echo=True)


@task
def release_finish(c, push=False):
    """Merge the current release/* branch into main (tagged) and develop, then delete it."""
    _finish(c, "release", push)


@task
def hotfix_finish(c, push=False):
    """Merge the current hotfix/* branch into main (tagged) and develop — or into an open
    release/* branch instead, if one exists — then delete it."""
    _finish(c, "hotfix", push)

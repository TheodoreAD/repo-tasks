"""Raw git plumbing implementing nvie's gitflow branch-naming and merge-back conventions.

PR mode (the default) is primary: every merge-back goes through a GitHub pull request via the `gh`
CLI, since a real team repo protects main/develop with required reviews/CI and a direct git
push/merge just gets rejected. Local mode (`local=True`) keeps the old direct-merge-and-push
behavior available for a single-person repo, trunk-based development, or fast local testing — no
`gh`, no network, no waiting on a human reviewer.

release/hotfix branches are cut *before* the version is bumped — the branch exists first, unbumped,
and the bump commit lands on the branch itself — matching nvie's actual sequence from "A successful
Git branching model", not bump-the-base-then-branch.

A PR can't merge synchronously, so PR-mode finish is two steps: `*_finish` opens the PR (into main)
and stops — no tag, no develop merge yet. `*_finalize`, run once a human has actually merged that PR
on GitHub, fetches main, tags it, and opens a second PR carrying the release/hotfix into develop —
or, per nvie, into any release branch that's still open, if this is a hotfix.

Every command that stops short of "the whole flow is done" — a PR was opened, a guard clause
tripped — prints exactly what to run next, so nobody has to read this file to find out."""

from invoke import task

from .version import _bump as version_bump
from .version import current_version, next_version


def _current_branch(c):
    return c.run("git rev-parse --abbrev-ref HEAD", hide=True).stdout.strip()


def _open_release_branch(c):
    names = c.run("git for-each-ref --format='%(refname:short)' refs/heads/release/*", hide=True).stdout.split()
    if len(names) > 1:
        raise ValueError(
            f"multiple release/* branches exist ({names!r}) — finish or delete the extra one before retrying"
        )
    return names[0] if names else None


def _next_steps(*lines):
    print("\nNext steps:")
    for line in lines:
        print(f"  - {line}")


def _open_pr(c, branch, base, title, body):
    c.run(f"git push -u origin {branch}", echo=True)
    result = c.run(f'gh pr create --base {base} --head {branch} --title "{title}" --body "{body}"', echo=True)
    return result.stdout.strip()


@task
def feature_start(c, name):
    """Branch feature/<name> off develop."""
    c.run(f"git checkout -b feature/{name} develop", echo=True)
    _next_steps(f"When ready: inv gitflow.feature-finish --name={name}")


@task
def feature_finish(c, name, local=False):
    """Merge feature/<name> back into develop. PR mode (default): opens a PR instead of merging
    directly — a protected develop branch rejects a direct push. --local keeps the old
    direct-merge-and-delete behavior, for a single-person repo or fast local testing."""
    branch = f"feature/{name}"
    if local:
        c.run("git checkout develop", echo=True)
        c.run(f"git merge --no-ff {branch}", echo=True)
        c.run(f"git branch -d {branch}", echo=True)
        return

    url = _open_pr(c, branch, "develop", f"Feature: {name}", f"Merging {branch} into develop.")
    _next_steps(
        f"PR opened: {url}",
        "Once it's approved and merged on GitHub, there's nothing else to run — this feature is done.",
    )


def _start(c, kind, base, bump, group):
    c.run(f"git checkout {base}", echo=True)
    branch = f"{kind}/{next_version(current_version(c, group=group), bump)}"
    c.run(f"git checkout -b {branch}", echo=True)
    version_bump(c, bump, group=group, tag=False)
    return branch


@task
def release_start(c, bump, group=None):
    """Branch release/<version> off develop, then bump the version on the release branch (no tag
    yet)."""
    branch = _start(c, "release", "develop", bump, group)
    _next_steps(f"When ready to ship: inv gitflow.release-finish (from the {branch} branch)")


@task
def hotfix_start(c, bump, group=None):
    """Branch hotfix/<version> off main, then bump the version on the hotfix branch (no tag
    yet)."""
    branch = _start(c, "hotfix", "main", bump, group)
    _next_steps(f"When ready to ship: inv gitflow.hotfix-finish (from the {branch} branch)")


def _local_finish(c, kind, push):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch you want to "
            "finish first"
        )
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


def _pr_finish(c, kind):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch you want to "
            "finish first"
        )
    version = branch.removeprefix(prefix)
    url = _open_pr(c, branch, "main", f"{kind.capitalize()} {version}", f"Merging {branch} into main.")
    _next_steps(
        f"PR opened: {url}",
        f"Once it's approved and merged on GitHub, run: inv gitflow.{kind}-finalize (from the {branch} branch)",
    )


@task
def release_finish(c, push=False, local=False):
    """PR mode (default): opens a PR merging the release branch into main and stops — run
    release_finalize once it's merged. --local does the old direct merge+tag+develop-merge+delete
    in one step; push (--local only) additionally pushes branches + tag to the remote."""
    if local:
        _local_finish(c, "release", push)
        return
    _pr_finish(c, "release")


@task
def hotfix_finish(c, push=False, local=False):
    """PR mode (default): opens a PR merging the hotfix branch into main and stops — run
    hotfix_finalize once it's merged. --local does the old direct merge+tag+develop-or-release-
    merge+delete in one step; push (--local only) additionally pushes branches + tag to the
    remote."""
    if local:
        _local_finish(c, "hotfix", push)
        return
    _pr_finish(c, "hotfix")


def _finalize(c, kind):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch whose PR you "
            "just merged, then re-run this"
        )
    tag = f"v{branch.removeprefix(prefix)}"

    c.run("git fetch origin main", echo=True)
    c.run("git checkout main", echo=True)
    c.run("git merge --ff-only origin/main", echo=True)
    c.run(f"git tag {tag}", echo=True)
    c.run(f"git push origin {tag}", echo=True)

    target = "develop"
    if kind == "hotfix":
        release_branch = _open_release_branch(c)
        if release_branch is not None:
            target = release_branch

    sync_branch = f"sync/{tag}"
    c.run(f"git checkout -b {sync_branch}", echo=True)
    url = _open_pr(c, sync_branch, target, f"Sync {tag} into {target}", f"Merging {tag} (main) into {target}.")
    _next_steps(
        f"PR opened: {url}",
        f"Once it's approved and merged on GitHub, the {kind} is fully finished — nothing else to run.",
    )


@task
def release_finalize(c):
    """Run once the PR from release_finish has been merged on GitHub: fetches and tags main, then
    opens a second PR carrying the release into develop. PR mode only — local mode's
    release_finish already does all of this in one step."""
    _finalize(c, "release")


@task
def hotfix_finalize(c):
    """Run once the PR from hotfix_finish has been merged on GitHub: fetches and tags main, then
    opens a second PR carrying the hotfix into develop — or into an open release/* branch instead,
    per nvie, if one exists. PR mode only — local mode's hotfix_finish already does all of this in
    one step."""
    _finalize(c, "hotfix")

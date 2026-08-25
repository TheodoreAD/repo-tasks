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

from invoke import Context, task

# `_bump` is the plain function behind the `bump` task; the underscore keeps it out of the CLI
# namespace, not out of sibling modules.
from .version import _bump as version_bump  # pyright: ignore[reportPrivateUsage]
from .version import current_version, next_version


def _current_branch(c: Context):
    return c.run("git rev-parse --abbrev-ref HEAD", hide=True).stdout.strip()


def _open_release_branch(c: Context):
    names = c.run("git for-each-ref --format='%(refname:short)' refs/heads/release/*", hide=True).stdout.split()
    if len(names) > 1:
        raise ValueError(
            f"multiple release/* branches exist ({names!r}) — finish or delete the extra one before retrying"
        )
    return names[0] if names else None


def _next_steps(*lines: str):
    print("\nNext steps:")
    for line in lines:
        print(f"  - {line}")


def _open_pr(c: Context, branch: str, base: str, title: str, body: str):
    c.run(f"git push -u origin {branch}", echo=True)
    result = c.run(f'gh pr create --base {base} --head {branch} --title "{title}" --body "{body}"', echo=True)
    return result.stdout.strip()


@task
def feature_start(c: Context, name: str):
    """Branch feature/<name> off develop."""
    c.run(f"git checkout -b feature/{name} develop", echo=True)
    _next_steps(f"When ready: inv gitflow.feature-finish --name={name}")


@task
def feature_finish(c: Context, name: str, local: bool = False):
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


def _start(c: Context, kind: str, base: str, bump: str, group: str | None):
    c.run(f"git checkout {base}", echo=True)
    branch = f"{kind}/{next_version(current_version(c, group=group), bump)}"
    c.run(f"git checkout -b {branch}", echo=True)
    version_bump(c, bump, group=group, tag=False)
    return branch


@task
def release_start(c: Context, bump: str, group: str | None = None):
    """Branch release/<version> off develop, then bump the version on the release branch (no tag
    yet)."""
    branch = _start(c, "release", "develop", bump, group)
    _next_steps(f"When ready to ship: inv gitflow.release-finish (from the {branch} branch)")


@task
def hotfix_start(c: Context, bump: str, group: str | None = None):
    """Branch hotfix/<version> off main, then bump the version on the hotfix branch (no tag
    yet)."""
    branch = _start(c, "hotfix", "main", bump, group)
    _next_steps(f"When ready to ship: inv gitflow.hotfix-finish (from the {branch} branch)")


def _local_finish(c: Context, kind: str, push: bool):
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


def _pr_finish(c: Context, kind: str):
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
def release_finish(c: Context, push: bool = False, local: bool = False):
    """PR mode (default): opens a PR merging the release branch into main and stops — run
    release_finalize once it's merged. --local does the old direct merge+tag+develop-merge+delete
    in one step; push (--local only) additionally pushes branches + tag to the remote."""
    if local:
        _local_finish(c, "release", push)
        return
    _pr_finish(c, "release")


@task
def hotfix_finish(c: Context, push: bool = False, local: bool = False):
    """PR mode (default): opens a PR merging the hotfix branch into main and stops — run
    hotfix_finalize once it's merged. --local does the old direct merge+tag+develop-or-release-
    merge+delete in one step; push (--local only) additionally pushes branches + tag to the
    remote."""
    if local:
        _local_finish(c, "hotfix", push)
        return
    _pr_finish(c, "hotfix")


def _finalize(c: Context, kind: str):
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
def release_finalize(c: Context):
    """Run once the PR from release_finish has been merged on GitHub: fetches and tags main, then
    opens a second PR carrying the release into develop. PR mode only — local mode's
    release_finish already does all of this in one step."""
    _finalize(c, "release")


@task
def hotfix_finalize(c: Context):
    """Run once the PR from hotfix_finish has been merged on GitHub: fetches and tags main, then
    opens a second PR carrying the hotfix into develop — or into an open release/* branch instead,
    per nvie, if one exists. PR mode only — local mode's hotfix_finish already does all of this in
    one step."""
    _finalize(c, "hotfix")


@task
def support_start(c: Context, version: str, base: str):
    """Branch support/<version> off <base> (a commit on main — a tag, SHA, or old release branch),
    for maintaining an old release line in parallel with ongoing development. Matches nvie's own
    git-flow tool's scope for this exactly (its README: "For support branches, the <base> arg must
    be a commit on master") — start only, no finish/merge-back task, because there isn't one: a
    support branch is a long-lived, permanently diverging line, not a short-lived branch that
    reconverges with develop/main. Branch creation itself is always local, same as
    release_start/hotfix_start — nothing to protect yet."""
    c.run(f"git checkout -b support/{version} {base}", echo=True)
    _next_steps(
        f"support/{version} created — protect it exactly like main: it ships to prod just the same.",
        f"To patch it: inv gitflow.support-hotfix-start --support={version} --bump=patch",
        "This branch never merges back into develop/main — that would pull old-line code forward into new development.",
    )


def _support_hotfix_start(c: Context, support: str, bump: str, group: str | None = None):
    target = f"support/{support}"
    c.run(f"git checkout {target}", echo=True)
    branch = f"support-hotfix/{support}/{next_version(current_version(c, group=group), bump)}"
    c.run(f"git checkout -b {branch}", echo=True)
    version_bump(c, bump, group=group, tag=False)
    return branch


@task
def support_hotfix_start(c: Context, support: str, bump: str, group: str | None = None):
    """Branch a patch off support/<support> to fix something on that maintenance line, then bump
    the version on the patch branch (no tag yet). support/* is protected exactly like main — it
    produces artifacts that ship to prod — so patching it goes through the same start/finish/
    finalize shape as a regular hotfix, just targeting the support branch instead of main. Never
    touches develop or the release-branch redirect rule: those exist to keep an active mainline
    release in sync, which has nothing to do with an already-diverged support line."""
    branch = _support_hotfix_start(c, support, bump, group=group)
    _next_steps(f"When ready to ship: inv gitflow.support-hotfix-finish --support={support} (from the {branch} branch)")


def _support_hotfix_branch_and_tag(c: Context, support: str):
    branch = _current_branch(c)
    prefix = f"support-hotfix/{support}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch for this "
            "support line first"
        )
    return branch, f"v{branch.removeprefix(prefix)}"


@task
def support_hotfix_finish(c: Context, support: str, push: bool = False, local: bool = False):
    """PR mode (default): opens a PR merging the patch branch into support/<support> and stops —
    run support_hotfix_finalize once it's merged. --local does the old direct merge+tag+delete in
    one step; push (--local only) additionally pushes the support branch + tag."""
    branch, tag = _support_hotfix_branch_and_tag(c, support)
    target = f"support/{support}"

    if local:
        c.run(f"git checkout {target}", echo=True)
        c.run(f"git merge --no-ff {branch}", echo=True)
        c.run(f"git tag {tag}", echo=True)
        c.run(f"git branch -d {branch}", echo=True)
        if push:
            c.run(f"git push origin {target}", echo=True)
            c.run(f"git push origin {tag}", echo=True)
        return

    url = _open_pr(c, branch, target, f"Support patch {tag}", f"Merging {branch} into {target}.")
    _next_steps(
        f"PR opened: {url}",
        f"Once it's approved and merged on GitHub, run: inv gitflow.support-hotfix-finalize --support={support} "
        f"(from the {branch} branch)",
    )


@task
def support_hotfix_finalize(c: Context, support: str):
    """Run once the PR from support_hotfix_finish has been merged on GitHub: fetches
    support/<support> and tags the new tip. No second PR — unlike release/hotfix finalize, a
    support patch never carries into develop. PR mode only — local mode's support_hotfix_finish
    already does all of this in one step."""
    _, tag = _support_hotfix_branch_and_tag(c, support)
    target = f"support/{support}"

    c.run(f"git fetch origin {target}", echo=True)
    c.run(f"git checkout {target}", echo=True)
    c.run(f"git merge --ff-only origin/{target}", echo=True)
    c.run(f"git tag {tag}", echo=True)
    c.run(f"git push origin {tag}", echo=True)
    _next_steps(f"{tag} tagged on {target} — this support patch is fully finished, nothing else to run.")

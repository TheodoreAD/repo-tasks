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

from .requirements import GH, NETWORK, requires
from .version import Version, current_version, next_version

# `_bump` is the plain function behind the `bump` task; the underscore keeps it out of the CLI
# namespace, not out of sibling modules.
from .version import _bump as version_bump  # pyright: ignore[reportPrivateUsage]


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


def _require_merged_pr(c: Context, branch: str, base: str):
    """Refuse to finalize until the PR from `branch` into `base` has actually merged. Without this
    the finalize sequence fails open: `git merge --ff-only origin/main` succeeds trivially when
    local and remote main are already equal, so the tag lands on the *old* tip and gets pushed —
    a wrong-commit tag, which is the one release state that can't be cleanly undone once anything
    (a consumer, a tag-triggered publish workflow) has seen it. The PR's state is the only signal
    that survives every merge strategy: a squash or rebase merge leaves no ancestry between the
    branch and main for `git merge-base` to find."""
    result = c.run(f"gh pr view {branch} --json state --jq .state", hide=True, warn=True)
    state = result.stdout.strip() if result.ok else "no PR found"
    if state != "MERGED":
        raise ValueError(
            f"the PR from {branch} into {base} is not merged yet (gh reports: {state}) — merge it on GitHub first, "
            "then re-run this; if it was never opened, run the matching *-finish task"
        )


def _require_tag_absent(c: Context, tag: str):
    """A release/hotfix about to be named after a version whose tag already exists means the base
    branch never received that version — almost always a `sync/<tag>` PR closed without merging,
    so develop still carries the pre-release version and the arithmetic lands on a number main
    already shipped. Catching it here, before any branch is cut, beats the alternative: nothing
    else notices until `git tag` fails inside *_finalize, after the PR has already been reviewed
    and merged."""
    existing = c.run(f"git tag --list {tag}", hide=True).stdout.strip()
    if existing:
        raise ValueError(
            f"tag {tag} already exists, so the version this branch would carry has already shipped — the base branch "
            f"is behind main. Merge (or recreate) the sync/{tag} PR into it first, then re-run this"
        )


@task
def feature_start(c: Context, name: str):
    """Branch feature/<name> off develop."""
    c.run(f"git checkout -b feature/{name} develop", echo=True)
    _next_steps(f"When ready: inv gitflow.feature-finish --name={name}")


@requires(GH, NETWORK)
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


def _start(c: Context, kind: str, base: str, bump: str, group: str | None, rc: bool):
    c.run(f"git checkout {base}", echo=True)
    # The branch is named after the *final* version it will ship, whether or not the bump lands
    # on rc1 first — the rc cycle happens on the branch, the name is what main gets.
    version = next_version(current_version(c, group=group), bump, rc=False)
    _require_tag_absent(c, f"v{version}")
    branch = f"{kind}/{version}"
    c.run(f"git checkout -b {branch}", echo=True)
    version_bump(c, bump, group=group, tag=False, rc=rc)
    return branch


@task(
    help={
        "bump": "major, minor, or patch",
        "group": "Version group to release (default: the repo's own root project)",
    }
)
def release_start(c: Context, bump: str, group: str | None = None):
    """Branch release/<version> off develop, then bump the version on the release branch to its
    first release candidate (`X.Y.0rc1`, no tag yet). `release-candidate` tags candidates from
    there; `release-finish` drops the rc when the release ships."""
    branch = _start(c, "release", "develop", bump, group, rc=True)
    _next_steps(
        f"To build a candidate for staging: inv gitflow.release-candidate (from the {branch} branch)",
        f"When ready to ship: inv gitflow.release-finish (from the {branch} branch)",
    )


@task(
    help={
        "bump": "major, minor, or patch",
        "group": "Version group to patch (default: the repo's own root project)",
        "rc": "Bump to rc1 and run a candidate cycle instead of going straight to the final version",
    }
)
def hotfix_start(c: Context, bump: str, group: str | None = None, rc: bool = False):
    """Branch hotfix/<version> off main, then bump the version on the hotfix branch (no tag
    yet). Straight to the final version by default — a hotfix ships as soon as it is reviewed;
    --rc opts into the same candidate cycle a release gets."""
    branch = _start(c, "hotfix", "main", bump, group, rc=rc)
    steps = [f"When ready to ship: inv gitflow.hotfix-finish (from the {branch} branch)"]
    if rc:
        steps.insert(0, f"To build a candidate for staging: inv gitflow.release-candidate (from the {branch} branch)")
    _next_steps(*steps)


def _release_branch(c: Context):
    """The current release/* or hotfix/* branch, or a raise naming what was expected — the
    candidate cycle runs on either, since a hotfix can opt into it."""
    branch = _current_branch(c)
    if not branch.startswith(("release/", "hotfix/")):
        raise ValueError(
            f"not on a release/* or hotfix/* branch (currently on {branch!r}) — candidates are cut from the branch "
            "that will ship"
        )
    return branch


@requires(NETWORK)
@task(help={"group": "Version group to bump (default: the repo's own root project)"})
def release_candidate(c: Context, group: str | None = None):
    """Cut the next release candidate on the current release/hotfix branch: bump `rcN` to
    `rcN+1`, tag `vX.Y.ZrcN+1` on the branch, and push branch and tag — so the tag-triggered
    workflows build and publish staging artifacts. The first candidate is `release-start`'s own
    rc1; this is every one after it."""
    branch = _release_branch(c)
    tag = f"v{next_version(current_version(c, group=group), 'rc')}"
    _require_tag_absent(c, tag)
    version_bump(c, "rc", group=group, tag=True)
    c.run(f"git push origin {branch} {tag}", echo=True)
    _next_steps(
        f"{tag} pushed — the tag-triggered workflows build it; deploy that to staging.",
        f"Another round: inv gitflow.release-candidate; ready to ship: inv gitflow.{branch.split('/', 1)[0]}-finish",
    )


def _drop_rc(c: Context, group: str | None):
    """Bump a release candidate to its final version before the branch merges into main — the
    version main receives is the one the branch was named after. A branch that never had an rc
    (a hotfix by default) has nothing to drop."""
    if Version.parse(current_version(c, group=group)).rc is not None:
        version_bump(c, "final", group=group, tag=False)


def _local_finish(c: Context, kind: str, push: bool, group: str | None):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch you want to "
            "finish first"
        )
    tag = f"v{branch.removeprefix(prefix)}"
    _drop_rc(c, group)

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


def _pr_finish(c: Context, kind: str, group: str | None):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch you want to "
            "finish first"
        )
    version = branch.removeprefix(prefix)
    _drop_rc(c, group)
    url = _open_pr(c, branch, "main", f"{kind.capitalize()} {version}", f"Merging {branch} into main.")
    _next_steps(
        f"PR opened: {url}",
        f"Once it's approved and merged on GitHub, run: inv gitflow.{kind}-finalize (from the {branch} branch)",
    )


_FINISH_HELP = {
    "push": "(--local only) also push branches and tag to the remote",
    "local": "Direct merge instead of a PR — a single-person repo or fast local testing",
    "group": "Version group being released (default: the repo's own root project)",
}


@requires(GH, NETWORK)
@task(help=_FINISH_HELP)
def release_finish(c: Context, push: bool = False, local: bool = False, group: str | None = None):
    """Drop the release candidate (`X.Y.0rcN` → `X.Y.0`, one more commit on the branch), then —
    PR mode (default) — open a PR merging the release branch into main and stop; run
    release_finalize once it's merged. --local does the old direct merge+tag+develop-merge+delete
    in one step; push (--local only) additionally pushes branches + tag to the remote."""
    if local:
        _local_finish(c, "release", push, group)
        return
    _pr_finish(c, "release", group)


@requires(GH, NETWORK)
@task(help=_FINISH_HELP)
def hotfix_finish(c: Context, push: bool = False, local: bool = False, group: str | None = None):
    """Drop the release candidate if the hotfix ran one (`--rc`), then — PR mode (default) — open
    a PR merging the hotfix branch into main and stop; run hotfix_finalize once it's merged.
    --local does the old direct merge+tag+develop-or-release-merge+delete in one step; push
    (--local only) additionally pushes branches + tag to the remote."""
    if local:
        _local_finish(c, "hotfix", push, group)
        return
    _pr_finish(c, "hotfix", group)


def _finalize(c: Context, kind: str):
    branch = _current_branch(c)
    prefix = f"{kind}/"
    if not branch.startswith(prefix):
        raise ValueError(
            f"not on a {prefix}* branch (currently on {branch!r}) — checkout the {prefix}* branch whose PR you "
            "just merged, then re-run this"
        )
    tag = f"v{branch.removeprefix(prefix)}"

    _require_merged_pr(c, branch, "main")
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


@requires(GH, NETWORK)
@task
def release_finalize(c: Context):
    """Run once the PR from release_finish has been merged on GitHub: fetches and tags main, then
    opens a second PR carrying the release into develop. PR mode only — local mode's
    release_finish already does all of this in one step."""
    _finalize(c, "release")


@requires(GH, NETWORK)
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
    version = next_version(current_version(c, group=group), bump, rc=False)
    _require_tag_absent(c, f"v{version}")
    branch = f"support-hotfix/{support}/{version}"
    c.run(f"git checkout -b {branch}", echo=True)
    version_bump(c, bump, group=group, tag=False, rc=False)
    return branch


@task
def support_hotfix_start(c: Context, support: str, bump: str, group: str | None = None):
    """Branch a patch off support/<support> to fix something on that maintenance line, then bump
    the version on the patch branch straight to its final value (no tag yet, no candidate cycle —
    a support patch is the narrowest change there is). support/* is protected exactly like main —
    it produces artifacts that ship to prod — so patching it goes through the same start/finish/
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


@requires(GH, NETWORK)
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


@requires(GH, NETWORK)
@task
def support_hotfix_finalize(c: Context, support: str):
    """Run once the PR from support_hotfix_finish has been merged on GitHub: fetches
    support/<support> and tags the new tip. No second PR — unlike release/hotfix finalize, a
    support patch never carries into develop. PR mode only — local mode's support_hotfix_finish
    already does all of this in one step."""
    branch, tag = _support_hotfix_branch_and_tag(c, support)
    target = f"support/{support}"

    _require_merged_pr(c, branch, target)
    c.run(f"git fetch origin {target}", echo=True)
    c.run(f"git checkout {target}", echo=True)
    c.run(f"git merge --ff-only origin/{target}", echo=True)
    c.run(f"git tag {tag}", echo=True)
    c.run(f"git push origin {tag}", echo=True)
    _next_steps(f"{tag} tagged on {target} — this support patch is fully finished, nothing else to run.")

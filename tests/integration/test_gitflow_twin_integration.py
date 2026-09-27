"""gitflow's PR mode against a real protected GitHub repo — the one call no other tier reaches.

Every other gitflow test stops short of `gh pr create`: the unit tier asserts command strings
against `MockContext`, and the manual dry runs used a local bare repo, which `gh` refuses as "not a
known GitHub host". This module drives the whole flow — `*_finish` opening the PR, `gh pr merge`,
`*_finalize` tagging and opening the sync PR — against `TheodoreAD/repo-tasks-gitflow-twin`, whose
`main` and `develop` carry a ruleset with an empty bypass list, so a direct push is rejected even
for its owner (see contributing/release-flow.md, "What has and hasn't been exercised for real").

Opt-in twice over: it lives in the integration tier, and it skips unless `REPO_TASKS_GITFLOW_TWIN`
names the twin (`owner/repo`), because it needs an authenticated `gh` and it writes to a public
repo — PRs, tags and merge commits that stay there. It derives its starting state from the twin
rather than assuming a clean one: the version comes off `develop`/`main` as they stand, feature
names are unique per run, and leftovers from an earlier failed run are left for a human to read.

Each test takes a fresh clone, never a shared one, so no test's outcome depends on which ran first.
The one test that needs a long-lived clone's history, a release finished and then a hotfix, builds
it inside itself.
"""

import os
import re
import subprocess
import time
import tomllib
import uuid
from pathlib import Path

import pytest

from repo_tasks import gitflow

_TWIN = os.environ.get("REPO_TASKS_GITFLOW_TWIN", "")

pytestmark = [
    pytest.mark.skipif(
        not _TWIN,
        reason="set REPO_TASKS_GITFLOW_TWIN=TheodoreAD/repo-tasks-gitflow-twin (needs `gh auth` and the network)",
    ),
    # Each flow is a handful of pushes and GitHub API calls; a hang is a network stall, not a slow test.
    pytest.mark.timeout(600),
]


def _run(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=root, check=check, capture_output=True, text=True)


def _git(root: Path, *args: str) -> str:
    return _run(root, "git", *args).stdout.strip()


@pytest.fixture
def twin(tmp_path, monkeypatch):
    """A fresh clone of the twin, as the working directory, with a local identity — the commits
    land in a public repo, so they carry a neutral author rather than whatever the machine has."""
    root = tmp_path / "twin"
    _ = _run(tmp_path, "gh", "repo", "clone", _TWIN, str(root))
    _ = _git(root, "config", "user.name", "repo-tasks twin test")
    _ = _git(root, "config", "user.email", "twin-test@example.invalid")
    monkeypatch.chdir(root)
    return root


def _checkout_latest(root: Path, branch: str) -> None:
    """What a developer does before starting a flow: `_start` branches off the *local* base, so a
    stale one would cut the release from an old commit."""
    _ = _git(root, "checkout", branch)
    _ = _git(root, "pull", "--ff-only", "origin", branch)


def _merge(root: Path, branch: str, method: str) -> None:
    """Merge the PR whose head is `branch`. Retried briefly because GitHub computes a new PR's
    mergeability asynchronously, and a merge requested in that window is refused; the last failure
    is raised with gh's own message."""
    for attempt in range(6):
        result = _run(root, "gh", "pr", "merge", branch, f"--{method}", check=False)
        if result.returncode == 0:
            return
        if attempt == 5:
            raise AssertionError(f"gh pr merge {branch} --{method} failed: {result.stderr}")
        time.sleep(5)


def _pr_state(root: Path, branch: str) -> str:
    return _run(root, "gh", "pr", "view", branch, "--json", "state", "--jq", ".state").stdout.strip()


def _remote_sha(root: Path, ref: str) -> str:
    """The commit `ref` points at on the remote. Peeled, because the two kinds of tag here differ:
    bump-my-version's rc tags are annotated, so the bare ref names a tag object, while `_finalize`'s
    `git tag` is lightweight and has no peeled line at all."""
    peeled = f"{ref}^{{}}"
    lines = _git(root, "ls-remote", "origin", ref, peeled).splitlines()
    refs = {name: sha for sha, name in (line.split() for line in lines)}
    return refs.get(peeled) or refs.get(ref, "")


def _version_on(root: Path, branch: str) -> str:
    _ = _git(root, "fetch", "origin", branch)
    text = _git(root, "show", f"origin/{branch}:pyproject.toml")
    version: str = tomllib.loads(text)["project"]["version"]  # pyright: ignore[reportAny]
    return version


def _pr_base(root: Path, branch: str) -> str:
    return _run(root, "gh", "pr", "view", branch, "--json", "baseRefName", "--jq", ".baseRefName").stdout.strip()


def _delete_remote_branches(root: Path, *branches: str) -> None:
    _ = _git(root, "push", "origin", "--delete", *branches)


def _assert_deleted(root: Path, branch: str) -> None:
    """`*_finalize` removes the branch it finished, in the clone and on origin."""
    assert _git(root, "branch", "--list", branch) == ""
    assert _remote_sha(root, f"refs/heads/{branch}") == ""


@pytest.mark.parametrize("branch", ["main", "develop"])
def test_direct_push_to_a_protected_branch_is_rejected(twin, branch):
    """The premise of the whole module: if this passes, PR mode's PRs are the only way in, and a bug
    that pushed directly instead would fail loudly here rather than succeed with a warning."""
    _ = _git(twin, "checkout", branch)
    _ = _git(twin, "commit", "--allow-empty", "-m", "twin test: a direct push the ruleset must reject")
    result = _run(twin, "git", "push", "origin", branch, check=False)
    assert result.returncode != 0
    assert "GH013" in result.stderr


def test_feature_round_trips_through_a_pr(c, twin):
    name = f"twin-{uuid.uuid4().hex[:8]}"
    _checkout_latest(twin, "develop")
    gitflow.feature_start.body(c, name=name)
    _ = _git(twin, "commit", "--allow-empty", "-m", f"twin test: feature {name}")

    gitflow.feature_finish.body(c, name=name)
    assert _pr_state(twin, f"feature/{name}") == "OPEN"
    _merge(twin, f"feature/{name}", "squash")

    assert _pr_state(twin, f"feature/{name}") == "MERGED"
    _delete_remote_branches(twin, f"feature/{name}")


@pytest.mark.parametrize("method", ["squash", "merge"])
def test_release_with_a_candidate_round_trips_through_prs(c, twin, method):
    """release_start → release_candidate → release_finish → merge → release_finalize → merge the
    sync PR, with the trunk PR merged both ways: `_require_merged_pr` claims the PR state is the
    one signal that survives every merge strategy, and a squash leaves no ancestry to fall back on."""
    _checkout_latest(twin, "develop")
    gitflow.release_start.body(c, bump="minor")
    branch = _git(twin, "branch", "--show-current")
    version = branch.removeprefix("release/")

    gitflow.release_candidate.body(c)
    assert _remote_sha(twin, f"refs/tags/v{version}rc2") == _git(twin, "rev-parse", "HEAD")

    gitflow.release_finish.body(c)
    assert _pr_state(twin, branch) == "OPEN"
    with pytest.raises(ValueError, match="not merged yet"):
        gitflow.release_finalize.body(c)

    _merge(twin, branch, method)
    gitflow.release_finalize.body(c)

    assert _remote_sha(twin, f"refs/tags/v{version}") == _remote_sha(twin, "refs/heads/main")
    assert _version_on(twin, "main") == version
    sync = f"sync/v{version}"
    assert _pr_state(twin, sync) == "OPEN"
    _assert_deleted(twin, branch)
    _merge(twin, sync, "merge")
    assert _version_on(twin, "develop") == version
    _delete_remote_branches(twin, sync)


def test_hotfix_round_trips_through_prs(c, twin):
    _checkout_latest(twin, "main")
    gitflow.hotfix_start.body(c, bump="patch")
    branch = _git(twin, "branch", "--show-current")
    version = branch.removeprefix("hotfix/")
    _ = _git(twin, "commit", "--allow-empty", "-m", f"twin test: hotfix {version}")

    gitflow.hotfix_finish.body(c)
    _merge(twin, branch, "squash")
    gitflow.hotfix_finalize.body(c)

    assert _remote_sha(twin, f"refs/tags/v{version}") == _remote_sha(twin, "refs/heads/main")
    sync = f"sync/v{version}"
    # Origin holds no release/* branch, so the sync PR targets develop.
    assert _pr_base(twin, sync) == "develop"
    _assert_deleted(twin, branch)
    _merge(twin, sync, "merge")
    assert _version_on(twin, "develop") == version
    _delete_remote_branches(twin, sync)


def test_start_refuses_a_version_whose_tag_already_exists(c, twin):
    """`_require_tag_absent` in the state it was written for: a release finalized, its sync PR not
    yet merged, so develop still carries the version before it and the next release_start computes
    a version main already shipped. Refused before any branch is cut, then the sync PR is merged so
    the twin is left as it was found."""
    _checkout_latest(twin, "develop")
    gitflow.release_start.body(c, bump="minor")
    release = _git(twin, "branch", "--show-current")
    version = release.removeprefix("release/")
    gitflow.release_finish.body(c)
    _merge(twin, release, "squash")
    gitflow.release_finalize.body(c)

    _checkout_latest(twin, "develop")  # current with origin, so only the tag check can refuse
    with pytest.raises(ValueError, match=re.escape(f"tag v{version} already exists")):
        gitflow.release_start.body(c, bump="minor")
    assert _git(twin, "branch", "--list", "release/*") == ""

    sync = f"sync/v{version}"
    _merge(twin, sync, "merge")
    _delete_remote_branches(twin, sync)


def test_a_reused_feature_name_resolves_to_its_open_pr(c, twin):
    """`_require_merged_pr` finds its PR by head-branch name, and a permanent repo reuses names. The
    unsafe answer is the older MERGED PR when a newer one is still OPEN — finalize would then tag a
    trunk the new work never reached. Two PRs from one name, the first merged, the second open."""
    name = f"twin-{uuid.uuid4().hex[:8]}"
    branch = f"feature/{name}"
    _checkout_latest(twin, "develop")
    gitflow.feature_start.body(c, name=name)
    _ = _git(twin, "commit", "--allow-empty", "-m", f"twin test: feature {name}, first PR")
    gitflow.feature_finish.body(c, name=name)
    _merge(twin, branch, "squash")
    _delete_remote_branches(twin, branch)

    _checkout_latest(twin, "develop")
    _ = _git(twin, "branch", "-D", branch)
    gitflow.feature_start.body(c, name=name)
    _ = _git(twin, "commit", "--allow-empty", "-m", f"twin test: feature {name}, second PR")
    gitflow.feature_finish.body(c, name=name)

    assert _pr_state(twin, branch) == "OPEN"
    _merge(twin, branch, "squash")
    assert _pr_state(twin, branch) == "MERGED"
    _delete_remote_branches(twin, branch)


def test_hotfix_during_an_open_release_syncs_into_the_release_branch(c, twin):
    """nvie's redirect: a hotfix finalized while a release is in flight merges back into the release
    branch rather than develop, so the release carries the fix to develop when it ships. Both
    branches bumped the version line, so the sync PR conflicts — expected, and resolved the way
    contributing/release-flow.md says, keeping the release branch's own version. Then the release
    finishes, which is what proves the fix reached develop."""
    _checkout_latest(twin, "develop")
    gitflow.release_start.body(c, bump="minor")
    release = _git(twin, "branch", "--show-current")
    release_version = release.removeprefix("release/")
    _ = _git(twin, "push", "-u", "origin", release)

    gitflow.hotfix_start.body(c, bump="patch")
    hotfix = _git(twin, "branch", "--show-current")
    hotfix_version = hotfix.removeprefix("hotfix/")
    _ = _git(twin, "commit", "--allow-empty", "-m", f"twin test: hotfix {hotfix_version} during {release}")
    gitflow.hotfix_finish.body(c)
    _merge(twin, hotfix, "squash")
    gitflow.hotfix_finalize.body(c)

    sync = f"sync/v{hotfix_version}"
    assert _pr_base(twin, sync) == release
    _ = _git(twin, "fetch", "origin", release)
    conflict = _run(twin, "git", "merge", f"origin/{release}", check=False)
    assert conflict.returncode != 0
    assert "pyproject.toml" in conflict.stdout
    _ = _git(twin, "checkout", "--theirs", "pyproject.toml")
    _ = _git(twin, "add", "pyproject.toml")
    _ = _git(twin, "commit", "--no-edit")
    _ = _git(twin, "push", "origin", sync)
    _merge(twin, sync, "merge")
    assert _version_on(twin, release) == f"{release_version}rc1"

    _checkout_latest(twin, release)
    gitflow.release_finish.body(c)
    _merge(twin, release, "merge")
    gitflow.release_finalize.body(c)
    assert _version_on(twin, "main") == release_version
    release_sync = f"sync/v{release_version}"
    assert _pr_base(twin, release_sync) == "develop"
    _merge(twin, release_sync, "merge")
    assert _version_on(twin, "develop") == release_version
    assert _run(twin, "git", "merge-base", "--is-ancestor", f"v{hotfix_version}", "origin/develop").returncode == 0
    _assert_deleted(twin, hotfix)
    _assert_deleted(twin, release)
    _delete_remote_branches(twin, sync, release_sync)


def test_hotfix_after_a_finished_release_in_the_same_clone_syncs_into_develop(c, twin):
    """The bug the fresh-clone tests could not see: PR mode's finalize left the finished release
    branch in the clone, and hotfix_finalize read local refs, so a later hotfix in the same clone
    opened its sync PR into a release that had already shipped. The fix never reached develop. One
    clone, a release finished end to end, then a hotfix."""
    _checkout_latest(twin, "develop")
    gitflow.release_start.body(c, bump="minor")
    release = _git(twin, "branch", "--show-current")
    release_version = release.removeprefix("release/")
    gitflow.release_finish.body(c)
    _merge(twin, release, "squash")
    gitflow.release_finalize.body(c)
    _assert_deleted(twin, release)
    release_sync = f"sync/v{release_version}"
    _merge(twin, release_sync, "merge")

    gitflow.hotfix_start.body(c, bump="patch")  # same clone; finalize left main current
    hotfix = _git(twin, "branch", "--show-current")
    hotfix_version = hotfix.removeprefix("hotfix/")
    _ = _git(twin, "commit", "--allow-empty", "-m", f"twin test: hotfix {hotfix_version} after {release}")
    gitflow.hotfix_finish.body(c)
    _merge(twin, hotfix, "squash")
    gitflow.hotfix_finalize.body(c)

    hotfix_sync = f"sync/v{hotfix_version}"
    assert _pr_base(twin, hotfix_sync) == "develop"
    _merge(twin, hotfix_sync, "merge")
    assert _version_on(twin, "develop") == hotfix_version
    _delete_remote_branches(twin, release_sync, hotfix_sync)


def test_start_refuses_a_base_behind_origin(c, twin):
    """A clone whose develop is behind origin's refuses to cut a release from it. Only the local
    branch is wound back, so nothing reaches the twin. The count is not pinned: develop's tip is
    usually a sync merge, so one step back along the first parent drops more than one commit."""
    _ = _git(twin, "checkout", "develop")
    _ = _git(twin, "reset", "--hard", "HEAD~1")
    with pytest.raises(ValueError, match=r"develop is \d+ commit\(s\) behind origin/develop"):
        gitflow.release_start.body(c, bump="minor")
    assert _git(twin, "branch", "--list", "release/*") == ""

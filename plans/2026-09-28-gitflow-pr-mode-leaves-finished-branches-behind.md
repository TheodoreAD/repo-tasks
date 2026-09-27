---
status: idea
updated: 2026-09-28
---

# gitflow's PR mode leaves finished branches behind, and hotfix_finalize reads them

## Context

Found while writing `tests/integration/test_gitflow_twin_integration.py`, by reading `gitflow.py`.
It has not been run.

Local mode's `_local_finish` ends with `git branch -d <branch>`. PR mode's `_finalize` never deletes
anything. It checks out the trunk, tags, and cuts `sync/<tag>`, so the finished `release/X.Y.0` and
the `sync/<tag>` branch both stay in the developer's clone indefinitely.

That matters because `_open_release_branch` decides where `hotfix_finalize` sends its sync PR by
listing **local** `refs/heads/release/*`:

- One finished release branch left behind: the hotfix's sync PR targets that dead branch instead of
  `develop`, so the fix never reaches develop. If the remote branch was already deleted,
  `gh pr create` fails on a missing base instead.
- Two or more: `_open_release_branch` raises `multiple release/* branches exist`, which is true and
  names the wrong cause.

Any clone that has finalized one release in PR mode is in the first state. The twin test avoids it
only because each test takes a fresh clone.

[UNVERIFIED: the failure as described. Read from the code, not reproduced. A twin test finalizing a
release and then a hotfix in one clone would show it.]

A second, smaller finding from the same run: `_start` branches off the **local** base (`develop` for
a release, the trunk for a hotfix) and never fetches, so a clone that is behind cuts from an old
commit silently.

## Open questions

[NEEDS CLARIFICATION: should `_finalize` delete the local `release/*`/`hotfix/*` branch once the tag
is pushed, matching local mode? Or should `_open_release_branch` ask the remote
(`git ls-remote origin 'refs/heads/release/*'`) rather than local refs? The first fixes the cause
and the second is robust to clones that already hold stale branches. Both may be wanted.]

[NEEDS CLARIFICATION: should `_start` fetch and fast-forward its base before branching, or refuse
when the local base is behind `origin/<base>`? nvie's git-flow has `-F`/`--fetch` for this, off by
default.]

## Recommended direction

Delete the finished branch at the end of `_finalize` (`git branch -D`, since a squash merge leaves
it unmerged by ancestry), and have `_open_release_branch` consult the remote, so existing stale
clones also stop misrouting. For `_start`, refuse when the local base is behind its upstream and
print the pull to run. That follows the module's print-what-to-run-next convention, rather than
fetching behind the user's back.

Reproduce it first with a twin test that finalizes a release and then a hotfix in **one** clone. The
existing twin tests take a fresh clone each, which is exactly why none of them hit it. The redirect
into a genuinely open release branch is already covered by
`test_hotfix_during_an_open_release_syncs_into_the_release_branch`, and the fix must keep that test
green.

---
status: landed
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

Reproduced 2026-09-28 against the twin, with the old `gitflow.py` and the new same-clone test.
Release 0.8.0 was finished and finalized, and then hotfix 0.8.1's sync PR (#30) opened with base
`release/0.8.0`. The twin was recovered by retargeting #30 to `develop` and merging it, and
`develop` then contained `v0.8.1`.

A second, smaller finding from the same run: `_start` branches off the **local** base (`develop` for
a release, the trunk for a hotfix) and never fetches, so a clone that is behind cuts from an old
commit silently.

## Open questions

~~[NEEDS CLARIFICATION:~~ should `_finalize` delete the local `release/*`/`hotfix/*` branch once the
tag is pushed, matching local mode? Or should `_open_release_branch` ask the remote
(`git ls-remote origin 'refs/heads/release/*'`) rather than local refs? The first fixes the cause
and the second is robust to clones that already hold stale branches. Both may be wanted.]

[DECISION: **both, plus deleting on origin**, chosen by the user 2026-09-28. Asking the remote alone
only moves the problem, since GitHub keeps a PR's head branch by default and origin collects
finished releases too. So `_finalize` deletes the branch locally (`-D`) and on origin when it is
still there, and `_open_release_branch(remote=True)` asks origin in PR mode. Origin is then
accurate, covers other people's clones, and is the only place a PR can target. Local mode keeps
local refs: it deletes its own branches and may have no remote. `support_hotfix_finalize` got the
same cleanup. Deliberately not done: deleting the local `sync/<tag>` branch. Finalize leaves you
standing on it, and it cannot affect routing.]

~~[NEEDS CLARIFICATION:~~ should `_start` fetch and fast-forward its base before branching, or
refuse when the local base is behind `origin/<base>`? nvie's git-flow has `-F`/`--fetch` for this,
off by default.]

[DECISION: **refuse when behind**, chosen by the user 2026-09-28. Auto fast-forward moves a branch
the task does not own, and an opt-in flag leaves the unsafe path as the default. The check degrades
rather than blocks: with no `origin` it is skipped, and a failed fetch is reported and skipped, so
an offline start still works. That degradation is this session's call, since the question did not
cover offline. The three start tasks now declare `NETWORK`.]

Landed in `a5fb2d4` (fix and unit tests, six of them failing against the previous code), `163fcc1`
(twin tests: same-clone reproduction, stale-base refusal, finalize-deletes assertions, tag-exists
rewritten) and `4fb5152` (release-flow). The twin run had nine tests green before the last two were
rewritten, and those two green after.

## Migrated to

- `src/repo_tasks/gitflow.py`: the docstrings of `_open_release_branch`, `_delete_finished_branch`
  and `_require_base_current` carry the failure, the choice and its reasons.
- `contributing/release-flow.md`, "Known bad states": the misrouted-sync-PR entry, with the recovery
  for consumers on older versions, and the stale-base refusal entry. The twin section's coverage
  list and fresh-clone rationale are updated to match.
- `tests/unit/test_gitflow.py` and `tests/integration/test_gitflow_twin_integration.py`: the
  regressions.

Deliberately not migrated: the reasoning about the gap between the two questions' options, which is
settled by the decisions above.

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

---
status: landed
updated: 2026-09-28
---

## Context

`gitflow.py`'s PR mode ([`contributing/release-flow.md`](../contributing/release-flow.md), "PR mode
(default) vs. local mode") has only ever been verified two ways: unit tests mocking `c.run`, and a
manual dry run against a **local bare repo** standing in for `origin` — which proved every git-only
step (push, fetch, ff-only merge, tag, sync-branch push) but stopped right at the actual
`gh pr create` call, since that needs a real GitHub-linked repo
(`none of the git remotes configured for this repository point to a known
GitHub host`).

`gh pr create` has now run against the twin in the `*_finish` and `*_finalize` paths of feature,
release and hotfix, 2026-09-28, through `tests/integration/test_gitflow_twin_integration.py`. The
release-candidate cycle ran with it: `release_start` to rc1, `release_candidate` tagging and pushing
rc2, `release_finish` dropping the rc, and `release_finalize` tagging the final on main's tip. The
`gh pr view` merge guard refused a finalize before the merge and allowed it after.

A second round the same day closed the rest, and all nine twin tests passed together.

- **The hotfix redirect.** With a release open in the same clone, `hotfix_finalize` opened its sync
  PR into `release/<v>`. The version-line conflict `contributing/release-flow.md` calls expected
  happened. Resolved on the sync branch in favour of the release's version, the release then
  finished and carried the hotfix's tag into `develop`. The PR-mode recovery is now written into
  release-flow.md's "Known bad states".
- **The tag-absent guard.** It fired on a tag fetched from the remote when a local trunk was wound
  back to an earlier release.
- **Head-branch name reuse.** One feature name was used for a merged PR and then a new open one, and
  `gh pr view <branch>` resolved to the **open** one. That is the safe answer for
  `_require_merged_pr`: an older merged PR cannot make finalize proceed past an unmerged newer one.

[DECISION: a **permanent** test-repo twin, not a throwaway repo created and deleted per run.
Repeated create/delete cycles risk GitHub's own soft-deletion and rename-cooldown quirks becoming
their own source of mess, and disposability buys nothing here. Leftover state from a run — stray
branches, an unmerged PR, a weird conflict — is a feature rather than something to clean up:
inspecting and fixing a real messy repo is itself how `gitflow.py`'s recovery paths and guidance
messages get improved.]

## Open questions

[DECISION: **all five questions below settled by the user 2026-09-26**, each as the recommended
direction had it:

- **`TheodoreAD/repo-tasks-gitflow-twin`, public.** Public because branch protection and rulesets
  are only available on public repos under GitHub Free; a private twin would need GitHub Pro to be
  protected, and protection is the point.
- **Seeded** with `pyproject.toml` plus a `tasks.py` importing `repo_tasks.ns`, so `inv gitflow.*`
  and `inv version.*` run end to end, the same shape as the manual dry runs.
- **Real branch protection on `main` and `develop`**, so a stray direct push is rejected the way a
  real protected repo would reject it. That is the case a bare local remote structurally cannot
  test.
- **Found through an env var and a doc:** an opt-in test tier (it needs `gh auth` and the network)
  reads the twin's name from an environment variable and skips when it is unset, and
  `contributing/release-flow.md` names the repo.
- **An automated test, not a manual dry run**, marked out of the fast default suite.

Creating the repo was approved by the user 2026-09-28, after the three amendments under "Recommended
direction" were written in. The questions this answers follow.]

~~[NEEDS CLARIFICATION:~~ repo name and visibility — under `TheodoreAD`, public or private? Naming
that signals "this is a permanent scratch target, not a real project" (something like
`repo-tasks-gitflow-twin`) probably matters more than usual, so nobody mistakes it for real work
later.]

~~[NEEDS CLARIFICATION:~~ seed content — does it need a real `pyproject.toml` + `tasks.py` wired to
`from repo_tasks import ns` (so `inv gitflow.*`/`inv version.*` actually run against it end to end,
same shape as the scratch repos used in the manual dry runs), or is a bare repo with just `main`
enough since we're only exercising `gh pr create`'s mechanics, not the version-bump content itself?]

~~[NEEDS CLARIFICATION:~~ does it need real branch protection rules on `main`/`develop` (mirroring
an actual protected team repo), so a stray `local=True` run or a bug can't silently succeed with a
direct push that a real protected repo would have rejected? Without protection, the twin only proves
`gh pr create`'s command construction is correct — it can't catch "this accidentally pushed directly
instead of opening a PR."]

~~[NEEDS CLARIFICATION:~~ how do future sessions/agents find and reuse it — a note in this repo's
`AGENTS.md`/`CONTRIBUTING.md` naming the repo directly, or something more structured (an env var a
test file reads, skipped when unset)?]

~~[NEEDS CLARIFICATION:~~ does verification against it become an actual automated test (skipped by
default, opt-in via an env var or marker, since it needs `gh auth` and network), or does it stay a
manual "run this by hand occasionally" dry run like the two rounds already done?]

## Recommended direction

Rough: one persistent GitHub repo under `TheodoreAD`, seeded like the scratch repos already used in
the manual dry runs (`pyproject.toml` + `tasks.py` importing `repo_tasks.ns`, editable-installed
from local source when testing a not-yet-released change). Document its name/URL somewhere durable
once created. Real branch protection on `main` and `develop` is probably worth the setup cost — it's
the one thing a local bare-repo stand-in structurally can't test, and it's exactly the scenario PR
mode exists for.

Three amendments, written in 2026-09-28 before the repo was created, each closing a gap between the
settled answers above and what they have to achieve:

[DECISION: **a ruleset with an empty bypass list, not classic branch protection.** The test runs as
the repo's owner, since `gh auth` is TheodoreAD, and classic protection lets an admin through by
default. That is exactly what this user's other personal repos already do: the push prints
"bypassing branch protection" and lands. A twin protected that way would let a stray direct push
succeed silently, which is the one failure the protection is there to catch. So `main` and `develop`
carry a ruleset requiring a pull request with **0 required approvals**, since a sole account cannot
approve its own PR, plus no deletion and no force-push, with nobody on the bypass list. The first
thing verified after setup is that a direct push to `main` is **rejected**.]

[DECISION: **the automated test derives its starting state from the twin; it does not assume a clean
one.** "Leftover mess is a feature" and "an automated test" pull opposite ways. A permanent repo
accumulates tags, `release/*` branches and open PRs, and `_require_tag_absent` or
`_open_release_branch` would then fail the next run for reasons unrelated to the code under test.
The test reads the current version off `develop`, works in a fresh clone under `tmp_path`, names
feature branches uniquely per run, and merges, finalizes and cleans up what it opened. Manual
messing around stays legitimate and separate, and a run that finds leftovers it did not create
reports them rather than deleting them.]

[DECISION: **no tag ruleset.** `_finalize` pushes the tag directly (`git push origin <tag>`), with
no PR, so a tag rule would reject the step that is working as designed. Branch rules only.]

The test merges its own PRs with `gh pr merge` between `*_finish` and `*_finalize`, since
`_require_merged_pr` refuses until `gh pr view` reports MERGED. The guard's claim to survive every
merge strategy held for both the squash and the merge-commit release run, 2026-09-28. Rebase merge
was not driven.

`gh pr view <branch>` resolves a PR by head-branch name, and a permanent twin reuses names across
runs. Settled by the second round, above: it prefers the open PR over an older merged one of the
same name.

A squash-merged release's `sync/<tag>` PR did **not** conflict with develop, 2026-09-28. Develop's
version line is untouched between syncs, because the bump commits live only on the release branch,
so the squash commit's version change applies cleanly. A develop that edited that line itself would
conflict, and should.

[PITFALL: bump-my-version's rc tags are **annotated** while `_finalize`'s `git tag` is
**lightweight**, so `git ls-remote origin refs/tags/<tag>` returns a tag object's SHA for one and a
commit's for the other. The twin test's first run failed on exactly that, comparing an rc tag to
`HEAD`. It peels (`<ref>^{}`) now. The mix is harmless to consumers, but anything comparing tags to
commits has to peel.]

[PITFALL: `_start` branches off the **local** base and never fetches it, so a clone whose `develop`
is behind cuts the release from an old commit, with nothing saying so. The twin test pulls first,
the way a developer would. Whether `_start` should fetch is a question for the new plan named above,
not for this one.]

### Setup sequence

1. `gh repo create TheodoreAD/repo-tasks-gitflow-twin --public`, with a description saying it is a
   test target for repo-tasks' gitflow tasks and not a project. Issues and wiki disabled.
2. Seed: `pyproject.toml` (a `[project]` with name and version `0.1.0`), `tasks.py` doing
   `from repo_tasks import ns`, and a README repeating the description. Push `main`, then branch and
   push `develop`.
3. Apply the ruleset to `main` and `develop`.
4. Verify a direct push to `main` is rejected, and record the result here.
5. Name the repo in `contributing/release-flow.md`'s verification section.

All five done 2026-09-28. Seed commit `8ad576e` is on both branches. The ruleset is id `24085532`:
deletion, non-fast-forward, and pull request with 0 approvals and all three merge methods allowed.
The API reports `bypass_actors: []` and `current_user_can_bypass: never`. As the owner, a direct
push of an empty commit to `main` and to `develop` was each refused with
`GH013: Repository rule violations found … Changes must be made through a pull request.`

The test tier followed the same day: `tests/integration/test_gitflow_twin_integration.py`, skipped
unless `REPO_TASKS_GITFLOW_TWIN` is set, with no new marker, since the integration directory is
already outside the default run. It ran 6 of 6 green, feature and the push-rejection checks first,
then release ×2 and hotfix in about two minutes. The twin ended with only `main` and `develop`,
seven merged PRs, tags `v0.2.0` and `v0.3.0` with their `rc2` tags, and `v0.3.1`.

The second round added the redirect, tag-guard and name-reuse tests. It ran 9 of 9 green in about
four minutes, and the twin again ended with only `main` and `develop` and no open PRs.

Nothing this plan set out to verify is left open. Rebase merge was not driven, and nothing here
depends on it. The gitflow bug the run surfaced is its own plan,
`plans/2026-09-28-gitflow-pr-mode-leaves-finished-branches-behind.md`.

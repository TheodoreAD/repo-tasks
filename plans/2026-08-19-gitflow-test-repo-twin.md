---
status: in-progress
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

[UNVERIFIED: `gh pr create` itself has never run against a real GitHub-linked repo — in either the
`*_finish` or the `*_finalize` path, nor the hotfix-redirect variant of the second PR. Everything
around it is confirmed; this one call is the gap, and closing it is this plan's entire purpose.]

[UNVERIFIED: the release-candidate cycle (`release_start` → rc1, `release-candidate` tagging and
pushing `vX.Y.0rcN` on the branch, `release_finish` dropping the rc, `*_finalize` tagging the final)
against a real remote — landed 2026-08-25 from the now-retired
`plans/2026-08-25-prerelease-versions.md`, unit-tested against exact command strings only, like the
rest of `gitflow.py`. The twin is where it gets driven for real; the `gh pr view` merge guard and
the `git tag --list` guard belong to the same run.]

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

[UNVERIFIED: the test has to merge its own PRs with `gh pr merge` between `*_finish` and
`*_finalize`, because `_require_merged_pr` refuses until `gh pr view` reports MERGED. That guard's
docstring claims the PR state "survives every merge strategy", and the claim is untested. Drive both
a squash merge and a merge commit.]

[UNVERIFIED: `gh pr view <branch>` resolves a PR by head-branch name, and a permanent twin reuses
names across runs: every feature run, and every `sync/<tag>`, if a tag is ever deleted and recut.
Which PR it picks when an older merged or closed PR shares the name is unknown, so unique feature
names are the working assumption until a run shows the behaviour.]

[UNVERIFIED: after a **squash** merge of a release PR, main's tip is a commit outside develop's
ancestry, so the `sync/<tag>` PR from main into develop may conflict on the version field. Local
mode only ever used `--no-ff` merges, so this has never come up.]

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

What is left is the opt-in test tier itself: the env var, the marker, and the run driving feature,
release with rc, and hotfix through `*_finish` → `gh pr merge` → `*_finalize`. It also has to settle
the three `UNVERIFIED` tags above.

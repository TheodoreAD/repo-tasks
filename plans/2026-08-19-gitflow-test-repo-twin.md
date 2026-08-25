---
status: idea
updated: 2026-08-25
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

**Not to be started now** — this is purely a placeholder for when that verification work resumes.

## Open questions

[NEEDS CLARIFICATION: repo name and visibility — under `TheodoreAD`, public or private? Naming that
signals "this is a permanent scratch target, not a real project" (something like
`repo-tasks-gitflow-twin`) probably matters more than usual, so nobody mistakes it for real work
later.]

[NEEDS CLARIFICATION: seed content — does it need a real `pyproject.toml` + `tasks.py` wired to
`from repo_tasks import ns` (so `inv gitflow.*`/`inv version.*` actually run against it end to end,
same shape as the scratch repos used in the manual dry runs), or is a bare repo with just `main`
enough since we're only exercising `gh pr create`'s mechanics, not the version-bump content itself?]

[NEEDS CLARIFICATION: does it need real branch protection rules on `main`/`develop` (mirroring an
actual protected team repo), so a stray `local=True` run or a bug can't silently succeed with a
direct push that a real protected repo would have rejected? Without protection, the twin only proves
`gh pr create`'s command construction is correct — it can't catch "this accidentally pushed directly
instead of opening a PR."]

[NEEDS CLARIFICATION: how do future sessions/agents find and reuse it — a note in this repo's
`AGENTS.md`/`CONTRIBUTING.md` naming the repo directly, or something more structured (an env var a
test file reads, skipped when unset)?]

[NEEDS CLARIFICATION: does verification against it become an actual automated test (skipped by
default, opt-in via an env var or marker, since it needs `gh auth` and network), or does it stay a
manual "run this by hand occasionally" dry run like the two rounds already done?]

## Recommended direction

Rough: one persistent GitHub repo under `TheodoreAD`, seeded like the scratch repos already used in
the manual dry runs (`pyproject.toml` + `tasks.py` importing `repo_tasks.ns`, editable-installed
from local source when testing a not-yet-released change). Document its name/URL somewhere durable
once created. Real branch protection on `main` and `develop` is probably worth the setup cost — it's
the one thing a local bare-repo stand-in structurally can't test, and it's exactly the scenario PR
mode exists for.

---
status: idea
updated: 2026-08-19
---

## Context

`gitflow.py`'s PR mode (`plans/2026-08-19-release-management.md` Design §2) has only ever been
verified two ways: unit tests mocking `c.run`, and a manual dry run against a **local bare repo**
standing in for `origin` — which proved every git-only step (push, fetch, ff-only merge, tag,
sync-branch push) but stopped right at the actual `gh pr create` call, since that needs a real
GitHub-linked repo
(`none of the git remotes configured for this repository point to a known
GitHub host`).

The obvious next step — spin up a throwaway GitHub repo, run the flow for real, delete it — was
explicitly rejected: repeated create/delete cycles risk GitHub's own soft-deletion/rename-cooldown
quirks turning into their own source of mess, and there's no benefit to it being disposable in the
first place. Decision from review: a **permanent** test-repo twin instead. Leftover state from a run
(stray branches, an unmerged PR, a weird conflict) is treated as a feature, not something to clean
up — inspecting and fixing a real messy repo is itself useful for improving `gitflow.py` and its
guidance messages.

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

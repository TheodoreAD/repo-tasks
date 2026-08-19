---
status: superseded by plans/2026-08-19-release-management.md
updated: 2026-08-19
---

## Context

`plans/2026-08-19-release-management.md`'s `gitflow.py` (landed) assumes `main`/`develop` are
plain local branches: `release_finish`/`hotfix_finish` do a local `git merge --no-ff` and, with
`--push`, push the merge commit directly. That breaks outright on a repo with branch protection
requiring pull requests — the direct push gets rejected server-side regardless of whether the merge
already happened locally.

Scope decision from review: this only matters for **team projects using the full gitflow
convention with protected branches** — a single-person repo or a repo using trunk-based development
with feature branches merged straight into `main` has no protection to work around, and keeps using
the existing local-merge path as-is. For the protected case, **GitHub only, via the `gh` CLI** — no
investment in GitLab/Merge Requests for now.

## Open questions

[NEEDS CLARIFICATION: `release_finish`/`hotfix_finish` are currently synchronous — one command
does merge + tag + cleanup. A PR-based flow can't be: opening a PR and waiting for review/CI is
inherently async. Does this become two separate tasks (e.g. `release_finish` opens the PR and stops;
a new `release_finalize` fetches `main` post-merge and tags it), or one task with a `--wait`
poll loop (`gh pr view --json state` until merged)?]

[NEEDS CLARIFICATION: tagging can't happen until _after_ the PR merges — GitHub's merge commit (or
squash commit) won't match whatever local merge commit we might have made ourselves, so the tag has
to land on whatever `main` looks like post-merge, fetched fresh. Where does the "wait for merge, then
fetch and tag" step live, and how does it know which PR/branch it's finishing for?]

[NEEDS CLARIFICATION: does `develop` need the same PR treatment if it's also protected? Or is the
`main` PR alone sufficient and `develop` gets fast-forwarded/rebased locally afterward (lower
friction, but only valid if `develop` isn't independently protected)?]

[NEEDS CLARIFICATION: the hotfix→open-release-branch redirect (`release-management.md` Design §2)
currently does a local merge into the release branch. Does that also need to become a PR when
protected, or is a release branch (not `main`/`develop`) assumed never to be protected itself?]

[NEEDS CLARIFICATION: how does a task know it's in "protected" mode — an explicit `--pr` flag per
invocation, a repo-level config flag (`repo-tasks.toml`?), or an auto-detect via `gh api
repos/{owner}/{repo}/branches/{branch}/protection`? Auto-detect is more ergonomic but adds a `gh
api` round trip to every finish call and a new failure mode if `gh` isn't authenticated.]

## Recommended direction

Rough, not designed: keep the existing local-merge path as the unconditional default (matches
`quality.py`'s house style — every task safe to run with zero config). Add an opt-in `--pr` flag (or
a `repo-tasks.toml`-level default, TBD per the open question above) that changes `release_finish`/
`hotfix_finish`'s behavior to: push the release/hotfix branch, `gh pr create --base main`, print the
PR URL, and stop — no local merge, no tag yet. A second task (name TBD) run once the PR is actually
merged does the fetch-`main`-and-tag step. `develop`'s merge-back likely follows the same shape if
it's also protected, otherwise stays a plain local fast-forward.

## Migrated to

All four open questions above got resolved and implemented directly in
`plans/2026-08-19-release-management.md`'s Design §2 ("PR mode (default) vs. local mode"), rather
than as a separate follow-on: PR mode is now the default (not opt-in — reverses this plan's rough
direction above), `local=True` is the opt-in alternative; finish is async two-step (`*_finish` opens
the PR and stops, `*_finalize` tags + opens the develop/redirect-target PR once a human has merged
it); `develop`'s merge-back always goes through a PR too, uniformly, no protection-status detection
needed. See that file for the actual design and `src/repo_tasks/gitflow.py` for the implementation.

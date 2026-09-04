---
status: landed
updated: 2026-09-05
---

# Releasing without a release branch every time

## Context

`gitflow.py` implements nvie's flow canonically: every release is a `release/X.Y.Z` branch off
`develop`, bumped on the branch, PR'd into `main`, tagged, synced back. The rc cycle also lives on
that branch ([`contributing/release-flow.md`](../contributing/release-flow.md), "The
release-candidate cycle", landed 2026-08-25). That is the right default for a team that stages
releases, and the wrong amount of ceremony for a team that ships `develop` (or `main`) whenever it
is green — trunk-based or GitHub-flow shaped teams, or a gitflow team for whom most releases are
"cut what's there, no stabilization needed".

Raised 2026-08-25 while settling where the rc cycle sits: keep the canonical shape as the default,
and explore this separately rather than fold a second mode into `release_start`.

## Decided 2026-09-04: both shapes ship, neither replaces the other

[DECISION: **the package supports gitflow _and_ trunk**, per the user: "we need to have both shapes,
gitflow with develop and ceremony and PRs, and owner-direct-to-main single dev style". So this is no
longer "which shape is worth supporting first" — the canonical flow stays exactly as it is, and the
trunk shape is added beside it. That also resolves the plan's framing: shape (b), tag-only releases
on `main`, is the one being added, because it is what "owner direct to main" means and it is the
only shape this repo can run today (no `develop` branch exists here, checked 2026-09-04).]

[DECISION: **the trunk shape gets its own namespace rather than a mode flag on `gitflow.*`.** The
plan's earlier lean was a `repo-tasks.toml` `[gitflow] model = "..."` key, and that was reasoning
about two near-duplicate trees. They are not near-duplicate: gitflow has twelve tasks
(feature/release/hotfix/support × start/finish/finalize, plus the rc cycle), and the trunk shape
needs roughly one — bump on `main`, tag, push. A mode key would make twelve task names conditionally
meaningful, and `inv --list` would advertise ten tasks that error in a trunk repo — a least-surprise
failure, and the reason this is not a cost argument. Two small namespaces is what `~/AGENTS.md` asks
for over an enum branching into near-duplicate trees.]

[PITFALL: the existing PR-vs-local axis is **already** orthogonal and must stay that way.
`gitflow`'s "PR mode (default) vs local mode" is about how a branch merges, not about which
branching model the repo uses — a trunk repo can want a PR too. Folding "PRs or not" into the model
choice would conflate two independent axes, which is the exact failure the decision above avoids for
the other one.]

### Naming: the two namespaces should read as the same class

The user's requirement, 2026-09-04: the trunk namespace should make it obvious it is an alternative
to gitflow, or that the two are in the same class — `trunk.release`, `git-trunk.release`, or a
shared root such as `integration.trunk.release`, the last being "a bit less user friendly when
typing, although of no consequence to an agent".

[DECISION: **refactor cost is not a criterion here**, per the user 2026-09-04: "we don't care about
cost of refactors usually. we care about ux and non-functional benefits like testability,
maintainability, extensibility, readability, simplicity etc. we also care about following the rule
of least surprise in ux." An earlier version of this section led with a measured 15-file rename
cost, which weighted the one thing that does not decide it. Recorded because the mistake is easy to
repeat: a number that is cheap to measure is not thereby a reason.]

**What the two things actually are.** Both are _git branching models_ — the umbrella nvie's original
post and Atlassian's docs both use. The one being added is trunk-based development in its solo
variant: commit straight to `main`, tag, release. It is specifically **not** GitHub Flow, which
branches and merges through a PR; that is a third model, and one that could plausibly be added
later.

### Why a shared root looks better than it is

[DECISION: **`sdlc` overclaims, and the overclaim is visible from `inv --list`.** SDLC spans
requirements, build, test, deploy and maintenance — and **ten of this package's sixteen namespaces
are already SDLC phases** sitting as siblings: `quality`, `test`, `dist`, `docker`, `helm`, `docs`,
`ci`, `deps`, `venv`, `configs`. A reader meeting `sdlc.gitflow.release-start` would reasonably
expect `sdlc.test` and `sdlc.quality` beneath it too, and they are visibly elsewhere. That is a
least-surprise failure by promising more than the namespace holds.]

[PITFALL: `workflow` as a root is worse than generic, it collides. This repo has real GitHub Actions
workflows and three tasks about them — `test.workflows`, `quality.workflow-check`,
`ci.check-actions`. `inv workflow.gitflow.release-start` beside `inv test.workflows` would make
"workflow" mean two unrelated things one namespace apart. `flow` inherits a weaker form of the same
problem, which is part of why it reads as generic.]

**The reframe that matters: a root answers a question asked once, and taxes every command forever.**
"Are these two alternatives?" is a _discovery_ question. Once a repo has chosen its model, nobody
working in it ever types the other one — so the root buys clarity at first contact and charges for
it on every invocation after. Against the stated criteria that trade is poor: it costs simplicity
(three levels where two do), readability (`sdlc.gitflow.release-start`), and buys nothing for
testability or maintainability, since nesting is a `Collection` wiring detail and the module
structure is identical either way.

### The alternative: make the class signal the _name_, with a shared suffix

[DECISION: **adopt `*flow` as the class marker** — `gitflow` (exists), `trunkflow` (new), and
`githubflow`/`gitlabflow` if a third model is ever wanted. The suffix is what says "these are
branching models", it needs no root, it keeps every command two levels, and it is the option that
extends cleanest, which is one of the criteria named. `gitflow` already carries the suffix, so the
convention is being noticed rather than invented.]

[PITFALL: sort adjacency in `inv --list` is a tempting tiebreaker and a bad one. Only `git-trunk`
(gap 0) and `githubflow` (gap 0) land next to `gitflow`; `trunkflow` and `trunk` sit four namespaces
away, behind `helm quality repo-tasks test`. But `githubflow` names a _different model_ than the one
being built, and `git-trunk` is an invented compound of the kind `~/AGENTS.md` warns off. A name
that is accurate beats a name that sorts well — the listing is scanned, not bisected.]

## Resolved — landed 2026-09-04, reconciled 2026-09-05

Everything this plan asked for was built on 2026-09-04, after its last edit, so its questions are
answered by code rather than by argument:

- **The namespace is `trunkflow.*`**, one task, `trunkflow.cut` (`e1d0306`): bump on `main`, tag,
  stop. `--push` opts into pushing; by default nothing leaves the machine (`cc49ebb`).
- **The GitHub Release task lives in `release.*`**, a module of its own (`a04b2ce`):
  `release.create` publishes an existing remote tag, and `release.push-tag` (`33017fa`) is the
  release gate as its own deliberate step. Neither flow owns them, because either flow's tag is
  published identically. The worry about `release.create` sitting one namespace from
  `gitflow.release-start` was accepted as the smaller mismatch: `publish` already means a package
  index in `dist`, and `version` is scoped to version strings.
- **Which shape**: (b), tag-only releases on `main`, is what shipped. (a) and (c) were not built,
  and the `sync/<tag>` question only arose for them — in (b) there is nothing to sync, which is the
  whole point. Not carried anywhere: a shape nobody asked for has no open plan.
- **This repo's `v0.2.0` was cut with it** (`cef6894`) and the tag is on origin. No GitHub Release
  was created: the user parked releases 2026-09-05 until there are real artifact stores to release
  into, and that is recorded in `plans/2026-09-04-versioning-policy.md`, which owns the release
  mechanism.

## Migrated to

- [`../contributing/release-flow.md`](../contributing/release-flow.md), "Two models ship, and a repo
  uses one" and "The trunk flow, end to end" — both-shapes decision, the namespace-not-mode
  decision, the orthogonal PR-vs-local axis, `cut` not pushing by default, and `release.py` being
  model-agnostic.
- [`../contributing/task-module-conventions.md`](../contributing/task-module-conventions.md), "A
  shared suffix marks a family of interchangeable modules" — the `*flow` suffix, and why `sdlc` and
  `workflow` roots were rejected.
- The module docstrings of `trunkflow.py` and `release.py` carry the same reasoning at the code.

Deliberately not migrated: the sort-adjacency pitfall (a name that is accurate beats one that sorts
well), the refactor-cost-is-not-a-criterion decision, and the three shape descriptions. The first
two are already the working rule in `~/AGENTS.md`'s naming and tool-choice sections; the shapes
describe designs that were not built.

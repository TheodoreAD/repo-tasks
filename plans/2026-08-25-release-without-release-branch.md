---
status: idea
updated: 2026-09-04
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
meaningful, and `inv --list` would advertise ten tasks that error in a trunk repo. Two small
namespaces is both honest and cheaper, and it is what `~/AGENTS.md` asks for over an enum branching
into near-duplicate trees.]

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

**The rename cost was measured rather than assumed, and it is smaller than this plan previously
implied.** `rg -c 'gitflow[._]'` over the repo: **15 files**, and heavily concentrated —
`tests/unit/test_gitflow.py` (41 hits) and `gitflow.py` itself (10) are most of it, with the rest
single-digit hits in plans, `contributing/` and `README.md`. The `invoke-task-conventions` skill's
53-file figure is from a 24-task rename in another repo and does not transfer.

| option                            | class signal                                                    | cost     | houses the shared release task? |
| --------------------------------- | --------------------------------------------------------------- | -------- | ------------------------------- |
| `gitflow.*` + `trunk.*`           | documentation only                                              | none     | no                              |
| `gitflow.*` + `git-trunk.*`       | shared `git` prefix, **and they sort adjacent** in `inv --list` | none     | no                              |
| `flow.gitflow.*` + `flow.trunk.*` | explicit and structural                                         | 15 files | **yes**                         |

[PITFALL: `trunk` alone does not sit next to `gitflow` in `inv --list`. Verified by sorting the real
namespace set — `gitflow, helm, quality, test, trunk, version` puts four namespaces between them, so
the "these two are alternatives" reading is available only to someone who already knows. `git-trunk`
does sort adjacent (`-` is 0x2D, before `f`), which is the one concrete argument for the invented
compound over the honest short name.]

[NEEDS CLARIFICATION: which of the three? The shared root is the only one that also solves a problem
this plan otherwise leaves open — `create-release` is wanted by **both** flows and belongs to
neither, so under the first two options it needs a third namespace of its own, while under a shared
root it is simply `flow.create-release`. Against it: every gitflow command grows by five characters,
and `trunk` and `git-trunk` are free. Note the mirroring argument is weaker than first stated —
`flow.gitflow.feature-start` still contains `gitflow feature start`, so nesting does not destroy the
`git flow feature start` echo, only lengthens it.]

## Open questions

[NEEDS CLARIFICATION: **superseded in part by the decision above** — both ship, and (b) is the one
being added. Retained for the shape descriptions, which are still the clearest statement of what
each involves. Which of these shapes is the one worth supporting first? (a) **release from develop**
— `gitflow.release-direct --bump minor`: bump on a short-lived branch that is immediately PR'd to
main with no rc cycle, i.e. today's `release_start` + `release_finish` collapsed into one command
and one PR; (b) **tag-only releases on main** — no `develop` at all, a bump PR against `main` and a
tag, GitHub-flow style, where `hotfix_*` is the only remaining flow; (c) **rc from develop** — rc
tags cut straight off `develop` (`vX.Y.0rc1` on a develop commit) with the release branch created
only if an rc needs fixing. (c) is what most "we don't need a release branch" requests actually
want, and it is the one that interacts with the dev-build scheme in the pre-release plan.]

**Answered 2026-09-04** — a separate set of tasks, in their own namespace, not a mode of the
existing ones. The reasoning is in the decision above; the short version is that the two trees are
not near-duplicates, so a mode key would leave ten task names advertised and inert in a trunk repo.

[NEEDS CLARIFICATION: how does the `sync/<tag>` merge-back change? In (a) it is unchanged; in (b)
there is nothing to sync; in (c) the rc tag is already on `develop`, so only the final needs syncing
— or the final is also tagged on `develop` and `main` just fast-forwards.]

## Recommended direction

**Superseded 2026-09-04.** This plan previously recommended waiting — the gate being "cut one real
release first, and see whether the release branch turns out to be ceremony or load-bearing". That
gate no longer decides anything, because the user has said **both** shapes are wanted regardless of
how that comparison would have come out. Waiting for evidence to choose between them is moot when
neither is being dropped.

What remains true from that reasoning, and is worth keeping: `git tag --list` is still empty, so the
rc cycle has never run for real, only against a local bare repo. That is now a reason to exercise
it, not a reason to wait.

The order of work, and it runs the other way round from what this plan assumed — the shape comes
first and the release comes out of it, because a hand-cut release would be evidence about nothing:

1. Add the trunk namespace (naming is the open question above). One task, roughly `release.cut`:
   bump on `main`, tag, push.
2. Add `dist.create-release` for the GitHub Release half — see
   `plans/2026-09-04-versioning-policy.md`, which owns the release mechanism and the versioning
   rule.
3. Cut this repo's `v0.2.0` with them, which exercises the trunk shape for real.
4. The gitflow shape stays untouched throughout and remains the default for a repo that has a
   `develop`. `hotfix_*` is unchanged in every shape: a hotfix is the one flow whose branch always
   earns its keep.

Prior art to check before designing: `git-flow-avh`'s `release finish` from a non-release branch,
`semantic-release`'s prerelease branches config (`develop` → `rc` channel), and how
`bump-my-version`'s `scm_info.distance_to_latest_tag` could stand in for a branch as "what is
unreleased".

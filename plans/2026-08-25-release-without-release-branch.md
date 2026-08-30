---
status: idea
updated: 2026-08-30
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

## Open questions

[NEEDS CLARIFICATION: which of these shapes is the one worth supporting first? (a) **release from
develop** — `gitflow.release-direct --bump minor`: bump on a short-lived branch that is immediately
PR'd to main with no rc cycle, i.e. today's `release_start` + `release_finish` collapsed into one
command and one PR; (b) **tag-only releases on main** — no `develop` at all, a bump PR against
`main` and a tag, GitHub-flow style, where `hotfix_*` is the only remaining flow; (c) **rc from
develop** — rc tags cut straight off `develop` (`vX.Y.0rc1` on a develop commit) with the release
branch created only if an rc needs fixing. (c) is what most "we don't need a release branch"
requests actually want, and it is the one that interacts with the dev-build scheme in the
pre-release plan.]

[NEEDS CLARIFICATION: is this a mode of the existing tasks (a `--direct` flag, a `repo-tasks.toml`
`[gitflow] model = "..."` key) or a separate set of tasks? A config key is closest to how the rest
of the package selects behavior (`repo-tasks.toml` for docker/helm), and it keeps `inv -l` from
listing two vocabularies; a flag keeps one code path per task but every caller has to remember it.]

[NEEDS CLARIFICATION: how does the `sync/<tag>` merge-back change? In (a) it is unchanged; in (b)
there is nothing to sync; in (c) the rc tag is already on `develop`, so only the final needs syncing
— or the final is also tagged on `develop` and `main` just fast-forwards.]

## Recommended direction

Rough. Do nothing until the pre-release plan has landed and been used once — the rc cycle on a
release branch may turn out cheap enough that (c) is not wanted.

**Half of that gate is now met, and the half that is not is the informative one.** Checked
2026-08-30: the pre-release work landed on 2026-08-25 and its plan has since been retired, so there
is no `plans/2026-08-25-prerelease-versions.md` to look for — the rc cycle is described in
[`../contributing/release-flow.md`](../contributing/release-flow.md). But `git tag -l` is empty:
this repo has never cut a release of any kind, so the rc cycle has been exercised only against a
local bare repo and never once for real. Until it has, there is no evidence about whether the
release branch is ceremony or load-bearing, which is the entire question this plan turns on. Waiting
is still the right call, and it is now waiting on one specific thing rather than two. If it is,
prefer (c) as a `repo-tasks.toml` `[gitflow]` setting over a per-call flag, and keep `hotfix_*`
unchanged in every shape: a hotfix is the one flow whose branch always earns its keep.

Prior art to check before designing: `git-flow-avh`'s `release finish` from a non-release branch,
`semantic-release`'s prerelease branches config (`develop` → `rc` channel), and how
`bump-my-version`'s `scm_info.distance_to_latest_tag` could stand in for a branch as "what is
unreleased".

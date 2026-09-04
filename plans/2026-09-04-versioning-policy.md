---
status: idea
updated: 2026-09-04
---

# What a version number means here, and cutting the first real release

## Context

Raised by the user 2026-09-04: dogfood releasing in this repo, since this repo is the mechanism the
rest of the family will use for it. Stay on `0.X.Y` until the package is fully developed, and **do
not spend effort deciding whether a change is breaking** — the family is evolving quickly and
changing course often, so that analysis is waste. The user's own default was minors only, `0.X.0` →
`0.(X+1).0`, with a stated reservation that it may look strange to consumers later.

The immediate motivation is concrete rather than tidiness. Consumers now pin this repo's reusable
security workflow by SHA (`contributing/quality-gate.md`), and `ci.check-actions` reports a stale
pin by asking `gh api repos/<owner>/<repo>/releases/latest`. With no releases that query returns
nothing, the pin is skipped as "nobody's release to track", and a pinned consumer goes stale
silently. **A release here is what turns that guard on.**

## What is actually true today, checked 2026-09-04

- **This repo has never released anything.** `git tag --list` is empty. The rc cycle has only ever
  been exercised against a local bare repo standing in for `origin`.
- **There is no `develop` branch** — `main` only, locally and on the remote. So `gitflow`'s
  canonical flow (branch `release/X.Y.Z` off `develop`, PR into `main`, tag, sync back) has no base
  to start from here without inventing one.
- **Nothing anywhere runs `gh release`.** `version.bump` commits and tags (`vX.Y.Z`, `tag=True` by
  default), and a tag is not a release: `releases/latest` stays empty. Tagging alone does not switch
  the currency check on.
- **`power-user-linux-setup` has a `stable` tag**, currently on a commit a few behind its `master`.
  It is a single _moving_ tag marking last-known-good, carries no version, and is the low-ceremony
  convention the user was thinking of.

[PITFALL: a git tag and a GitHub Release are different objects, and only the second answers
`releases/latest`. `inv version.bump minor` produces the tag and stops, so a release flow that ends
there looks complete, pushes a real `v0.2.0`, and leaves every pinned consumer exactly as unwatched
as before. This is the trap most likely to make the first release feel like it worked while
delivering none of the reason for cutting it.]

## The proposal: derive minor-vs-patch from the shipped surface, not from breakage

The user is right that breaking-change analysis is waste here, and SemVer agrees: under `0.x`
anything may change at any time, so nothing is being violated by not doing it. That frees
minor-vs-patch to carry a **different and more useful signal**, and this package happens to have an
unusually crisp one available.

A consumer of `repo-tasks` inherits exactly four things, and nothing else in this repo is visible to
them:

1. `src/repo_tasks/configs/*` — the files `configs.pull` writes into their repo.
2. The `repo-tasks-quality` dependency group — what `configs.ensure-deps` splices into their
   `pyproject.toml`.
3. The `inv` task names — the CLI contract, cited in their docs, CI and Dockerfiles.
4. `.github/workflows/security-reusable.yml` — now called by other repos.

So:

- **minor (`0.X.0`)** — any of those four changed. "Pulling this will change something in your
  repo."
- **patch (`0.X.Y`)** — none of them did. "Upgrading is a no-op for you; it is internals, docs,
  tests or a fix behind an unchanged surface."

Why this beats the two obvious alternatives:

- **Against minors-only**: it answers the question a consumer actually has, which is not "will this
  break me" but "do I need to run `configs.pull` and read a diff". With minors-only every release
  looks like it might touch their repo, so the number stops being information.
- **Against SemVer breakage semantics**: it needs no judgement at all. "Did any of these four things
  change" is a `git diff --name-only <last tag>..HEAD` over a path list plus a comparison of task
  names — mechanically checkable, and therefore enforceable by a task rather than by remembering.
- **It does not look strange later.** At 1.0 exactly one rule is added — breaking goes to major —
  and minor and patch keep the meanings consumers already learned. Nothing has to be re-explained.

[DECISION: **adopted by the user 2026-09-04.** Minor and patch here mean "the shipped surface moved"
and "it did not", never SemVer's breaking and non-breaking. That has to be stated wherever a
consumer meets it, because the parts look like SemVer's and mean something else — the difference is
not visible from the number.]

[UNVERIFIED: the claim that the four surfaces are the whole consumer contract. It is derived from
reading `configs.py` and the `repo-tasks-quality` group rather than from an audit of what a consumer
repo actually reads. `bootstrap.sh` is a fifth candidate — consumers copy it — and the `Version`
parts in `version.py` are arguably a sixth for anyone importing the package rather than running its
tasks. Settle the list before writing it into `contributing/`, because the rule is only as good as
the enumeration.]

[DEFERRED: **a task that computes the part for you.** `inv version.next-part --since v0.2.0` diffing
the four surfaces and printing `minor` or `patch` is the natural end state, and it is exactly the
kind of thing this package exists to hand other repos. Not needed for the first release — the answer
for a first release is trivially "whatever we call it" — and designing it before the rule has been
used once would be the wrong order.]

## Open questions

**Answered 2026-09-04, in the plan that owns it** —
`plans/2026-08-25-release-without-release-branch.md`. Both shapes ship: the canonical gitflow one is
untouched, and a trunk shape is added beside it in its own namespace. This repo will use the trunk
one, since it has no `develop`. What is still open there is the namespace's name.

## Releasing is manual, and the task is the primitive

[DECISION: **a release is never automatic**, per the user 2026-09-04 — not every version merits one,
and a version that does may not want it immediately. So nothing tag-triggered: no workflow that
fires because a `v*` tag appeared. Both entry points are deliberate acts.]

[DECISION: **a task, with a `workflow_dispatch` workflow calling it** — not two implementations of
the same thing. The task is the primitive because an agent can run it and because it is testable the
way every other task here is; the workflow exists so a human can cut a release from GitHub's UI
without a checkout. The workflow bootstraps and runs the task.]

That is the opposite call from `security-reusable.yml`, which deliberately runs `uv audit --locked`
raw rather than `inv deps.audit`, and the two are consistent once the reason is named:

|                          | security workflow        | release workflow                                       |
| ------------------------ | ------------------------ | ------------------------------------------------------ |
| logic behind the command | none — one uv subcommand | resolving the tag, refusing a duplicate release, notes |
| how often it runs        | every push to `main`     | rarely, by hand                                        |
| bootstrap cost           | dominates a 0.7s job     | irrelevant                                             |

So the rule is not "always avoid `inv` in CI" — it is that a workflow duplicates a command only when
the command has no logic worth single-sourcing and the bootstrap would dominate. Here both are the
other way round, and duplicating `gh release create` plus its guards in YAML is exactly the drift
the audit workflow's own test exists to prevent.

### The task

`inv dist.create-release [--tag vX.Y.Z]`, defaulting to the most recent tag.

[DECISION: `dist`, not `version` or `gitflow`. Applying the `invoke-task-conventions` skill: `dist`
owns artifacts leaving this repo (`dist.build`, `dist.publish`, `dist.list-versions`), and a GitHub
Release is exactly that. `version.py` owns version _strings_ and their three spellings; `gitflow.py`
owns branch flow. Verb-first per rule 1, and `create` is both the shared vocabulary's verb and
`gh
release create`'s own.]

[PITFALL: do not name it `dist.release`. That is noun-only, which rule 1 forbids, and it would read
as a sibling of `gitflow.release-start`/`release-finish`/`release-candidate` — a different concept
in a different flow. `dist.publish` is also taken and means "upload to a package index", so reusing
`publish` here would give one verb two targets.]

A `--tag` argument rather than always taking `HEAD`'s tag is what makes "release later, or never"
work: a tag can sit unreleased indefinitely and be released when someone decides it should be.

[NEEDS CLARIFICATION: does `repo-tasks` want a moving `stable` tag as well? It is a different
mechanism for a different question — `stable` says "what should I install", version tags say "what
am I pinned to" — so they are complementary rather than alternatives. Probably not needed here,
since consumers pin SHAs and the currency check reads releases, but it is the convention the user
named and worth ruling in or out deliberately.]

## Is a release needed now? No — checked, and the urgency was overstated

The case for cutting one immediately was that SHA-pinned consumers go unwatched while
`releases/latest` is empty. **Checked 2026-09-04: there are no SHA-pinned consumers.** The only
caller of `security-reusable.yml` anywhere is this repo's own `security.yml`, which uses the
relative `./` form and carries no ref at all. So the currency check has nothing to watch either way,
and releasing today would improve nothing that exists.

[DECISION: the release waits for the mechanism, not the other way round. Cutting `v0.2.0` by hand
now — `git tag` plus a `gh release create` typed at a prompt — would be the one thing this exercise
is not for: the point is to dogfood the flow other repos will use, and a hand-cut release is
evidence about nothing. Build `dist.create-release` and the trunk release shape first, then use
them.]

The release does become necessary the moment the first external caller pins a SHA, which is the
`scaffoldapy` template plan. That is the real trigger to watch.

## Recommended direction

In order, each step being the prerequisite of the next:

1. **Settle the surface enumeration** (the `UNVERIFIED` tag above). The rule is only as good as the
   list, and it is cheap to get right before anything is written into `contributing/`.
2. **Decide the release shape** — `plans/2026-08-25-release-without-release-branch.md`, now that the
   user has said both shapes are wanted rather than one replacing the other.
3. **Build `dist.create-release`**, plus the `workflow_dispatch` workflow that calls it.
4. **Cut `v0.2.0` with them.** It is a minor under the adopted rule whichever way the enumeration
   settles: surfaces 1, 2 and 4 have all moved since `0.1.0` was set — the packaged-tests configs,
   the ruff `banned-api` entry, `pytest-timeout` in the manifest, and the reusable workflow itself.
5. **Write the policy into `contributing/release-flow.md`**, stating plainly that minor and patch
   here mean "surface moved" and "surface did not", not SemVer's breaking and non-breaking.
6. Let that release be the evidence `2026-08-25-release-without-release-branch.md` has been waiting
   for, and close its question with what happened rather than with a prediction.

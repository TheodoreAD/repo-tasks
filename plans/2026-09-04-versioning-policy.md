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

[NEEDS CLARIFICATION: which release shape, given there is no `develop`? This is the same question as
`plans/2026-08-25-release-without-release-branch.md`, which listed three shapes and chose to wait
for exactly this evidence — a real release. Its shape (b), "tag-only releases on `main`, GitHub-flow
style", is the only one that runs here without inventing a `develop` branch, and it matches how this
repo actually works (direct pushes to `main`, no PR review, per `~/AGENTS.md`). Deciding it here
would unblock that plan rather than duplicate it.]

[NEEDS CLARIFICATION: does the release create a GitHub Release, and by what? The tag is one command
(`inv version.bump minor`); the Release is not currently produced by anything. Either a
`gh release
create` step in a new task, or a tag-triggered workflow. The workflow is the shape the
family already uses for tag-triggered publishing and would keep the credential story consistent; a
task is simpler and this repo has no publish workflow live yet.]

[NEEDS CLARIFICATION: does `repo-tasks` want a moving `stable` tag as well? It is a different
mechanism for a different question — `stable` says "what should I install", version tags say "what
am I pinned to" — so they are complementary rather than alternatives. Probably not needed here,
since consumers pin SHAs and the currency check reads releases, but it is the convention the user
named and worth ruling in or out deliberately.]

## Recommended direction

1. Adopt the surface-derived rule above, and settle the enumeration first (the `UNVERIFIED` tag).
2. Cut `v0.2.0` by shape (b) — bump on `main`, tag, and create a GitHub Release — because the
   current `0.1.0` has never been released and the packaged-tests and security-workflow changes have
   already moved surface 1, 2 and 4 since it was set.
3. Write the policy into `contributing/release-flow.md` where consumers and future agents will meet
   it, stating plainly that minor and patch here mean "surface moved" and "surface did not", **not**
   SemVer's breaking and non-breaking.
4. Let that first release be the evidence `plans/2026-08-25-release-without-release-branch.md` has
   been waiting for, and close its question with what actually happened rather than with a
   prediction.

---
status: idea
updated: 2026-08-23
---

## Context

`contributing/` was created by the now-retired plan-retirement pass, populated by migrating the
durable content out of six retiring plans. Migration can only carry across what those plans actually
contained, which is less than the four files' stated scopes describe.

This plan tracks those gaps. It exists because the alternative — leaving "TODO: document recovery"
lines inside the `contributing/` files — is the exact failure mode the plan-docs convention forbids:
prose has no status field, so nothing ever prompts a return visit. The `contributing/` files stay
silent about what they don't cover; the silence is recorded here instead.

Each gap below is a real absence, not a stub. Fixing any one of them is independent work — this is
deliberately a checklist, not a single design.

## Open questions

### `contributing/versioning.md` — pre-release versions across three formats

The largest gap, and the only one that is a design question rather than a writing task.

[NEEDS CLARIFICATION: this repo has no pre-release/dev-version convention at all, and the three
artifact kinds disagree on how to spell one. PEP 440 wants `1.0.0rc1`/`1.0.0.dev1`; Helm chart
versions must be strict SemVer 2 (`1.0.0-rc1`); Docker tags forbid `+` outright, so SemVer build
metadata cannot round-trip into an image tag. `version.py` currently assumes all three agree, which
is true for plain `X.Y.Z` and false the moment a pre-release exists. Does the repo (a) adopt a
convention and translate per artifact kind at write time, (b) restrict itself to `X.Y.Z` releases
only and document that as a deliberate limitation, or (c) something narrower — e.g. pre-releases
allowed for python only, since that is the one artifact with an index that understands them?]

[NEEDS CLARIFICATION: option (a) above would make `version.py` generate a bump-my-version config
that customizes `parse`/`serialize`. That directly invalidates the assumption documented in
`contributing/versioning.md`'s "Why `next_version` is hand-rolled" — plain arithmetic is only safe
because the generated config never customizes them. Does `next_version` then shell out to
`bump-my-version show --increment` after all, or is the arithmetic extended to understand the chosen
pre-release scheme?]

### `contributing/release-flow.md` — recovery from bad states

The file documents one recovery procedure (the version-line merge conflict during a hotfix redirect)
because it is the only one any plan ever wrote down. The rest are reachable states with no
documented way out.

[NEEDS CLARIFICATION: what is the recovery procedure for each of these? (1) an abandoned release
branch — the branch exists with a bump commit on it, `develop` and `main` are untouched, and someone
decides not to ship; (2) a tag pushed to the wrong commit, which is the irreversible-ish one since
the tag may already be fetched elsewhere; (3) `*_finalize` run before the PR actually merged, where
`git merge --ff-only origin/main` fails — is failing there sufficient, or does it leave partial
state?; (4) a `sync/<tag>` PR closed without merging, leaving `main` tagged and released but
`develop` never catching up. Each needs writing up, and (3)/(4) need checking against the actual
code rather than reasoned about.]

[NEEDS CLARIFICATION: should any of these become guard clauses that print via `_next_steps()` rather
than documentation a human has to find? The "stop loudly and say what to run next" convention argues
that a task which _can detect_ a bad state should say so at the point of failure. That would move
some of this out of `contributing/` and into `gitflow.py` — a code change, not a docs change, and
arguably the better fix for (3) specifically.]

### `contributing/test-tiers.md` — resolved 2026-08-23

The clean-OS mutating tests landed (`tests/integration/test_clean_os_user_effects.py`), and the
section gained its "What the tier covers" and "Fixture scope" subsections in the same pass — this
file's test-tiers gap is closed.

### `contributing/task-module-conventions.md` — assembled, needs a coherence pass

[NEEDS CLARIFICATION: this file was assembled from conventions scattered across five different
plans, none of which stated them as a set. It reads consistently, but nothing has verified that the
rules are actually _complete_ or that the code follows all of them uniformly. Worth one deliberate
pass: grep each rule against every module and confirm it holds — e.g. does every task really pass
`echo=True`, does every discovery path really raise rather than guess on an unknown `--project`? Any
rule the code doesn't actually follow is either a bug to fix or a rule to drop.]

### Cross-cutting

[NEEDS CLARIFICATION: does `contributing/` need an index/README of its own, or is four files few
enough that `AGENTS.md`'s pointers are sufficient? Adding one now is cheap; adding one at eight
files is a retrofit. Decide before the count grows.]

## Recommended direction

Rough. Take the versioning pre-release question first — it is the only gap that is currently a live
correctness risk rather than missing prose, since `version.py` will silently produce an invalid Helm
chart version the first time anyone bumps to a release candidate. The rest can be written whenever
the relevant work next brings someone into that file.

Do not treat this plan as a blocker on retiring the six original plans; those retire on the strength
of what actually migrated, and this tracks what was never there to migrate in the first place.

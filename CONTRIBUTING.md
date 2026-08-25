# Contributing to repo-tasks

The nexus for "why is it built this way": [`README.md`](README.md) says what the tasks are and how
to use them, [`AGENTS.md`](AGENTS.md) holds the instructions an agent needs up front, and the files
under `contributing/` hold the reasoning — settled decisions, what was rejected, and the pitfalls
confirmed by hitting them. Read the relevant one before changing behavior it covers.

## Before a change is done

`inv quality.precommit` — fix, then check, then the unit tier. Every commit, markdown-only ones
included (`dprint` reflows prose, and a skipped gate is the most common red CI run in this family).
`inv quality.check` is the same gate without mutations; `inv -l` lists the individual tasks.

## Where the reasoning lives

- [`contributing/task-module-conventions.md`](contributing/task-module-conventions.md) — the rules
  every task module follows: never silently mutate, single-writer ownership of `uv.lock` and version
  fields, no-op cleanly when an artifact kind is absent, zero-config defaults, stop loudly and say
  what to run next, one module per facility, sibling imports.
- [`contributing/release-flow.md`](contributing/release-flow.md) — how gitflow is applied (branch
  first, then bump; PR mode as two steps; the hotfix redirect; `support/*`), the known bad states
  and how to get out of each.
- [`contributing/versioning.md`](contributing/versioning.md) — semver bumped explicitly, version
  groups, the python/docker/helm format split, why bump-my-version, and why `uv.lock` moves with the
  bump.
- [`contributing/release-workflows.md`](contributing/release-workflows.md) — how images reach GHCR,
  why the release workflows are dispatched by hand, how to check a workflow locally first.
- [`contributing/test-tiers.md`](contributing/test-tiers.md) — the unit / integration / clean-OS
  split and its fixtures.
- [`contributing/type-checking.md`](contributing/type-checking.md) — why the basedpyright profile is
  tiered rather than relaxed, why `invoke-stubs` exists and ships the way it does, every rule level
  that deviates from `recommended`, and what `failOnWarnings` demands of new code.
- [`contributing/consumer-sweep.md`](contributing/consumer-sweep.md) — who consumes this package,
  why a push to `main` is a deploy to all of them, and the commands that walk each one forward after
  the shared tool manifest or a shipped config changes.

Organized by the question a reader arrives with, not by the plan that produced the content — a new
file is worth adding when a question has no home above, not per feature.

## Work that is not done yet

`plans/` — one file per idea or design, with a `status` in its frontmatter. Anything unfinished
belongs there and never as prose in the files above. Find it without opening files:

```shell
rg '^\s*[-*]?\s*\[DEFERRED:' plans/              # the backlog
rg '^\s*[-*]?\s*\[NEEDS CLARIFICATION:' plans/   # open questions
rg '^\s*[-*]?\s*\[UNVERIFIED:' plans/            # unproven claims
```

When a plan lands, its durable content moves into the files above and the plan is deleted;
`[DECISION:` and `[PITFALL:` tags in `contributing/` mark what came from where.

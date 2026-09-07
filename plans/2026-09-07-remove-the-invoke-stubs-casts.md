---
status: landed
updated: 2026-09-07
source_repo: github.com-personal/invoke-stubs
source_session: 65f8437a-a90e-41c6-9b1f-9b43d713ed9b.jsonl
source_moment: 2026-09-07T12:02:09Z
---

# The 14 casts invoke-stubs 0.2.0 cost are unnecessary on 0.3.0

## Context

Taking invoke-stubs 0.2.0 into this repo produced 37 `reportAny` errors, all on
`ns.collections["<name>"]` lookups in `tests/unit/test_init.py`, and the session working here closed
them with `cast(Collection, ns.collections["<name>"])` in 14 places — the shape
`tests/unit/test_cli.py` already used for the identical lookup. That was the right call for the
version available at the time.

invoke-stubs 0.3.0 makes `Lexicon` generic and declares `Collection.collections` as
`Lexicon[Collection]` and `.tasks` as `Lexicon[Task[Any]]`, so those lookups are typed at the source
and every one of the casts is now redundant.

**Nothing in this repo's gate will say so.** `reportUnnecessaryTypeIgnoreComment` is an error here
and would have named a stale `# pyright: ignore`, but a redundant `cast` is not a suppression and no
basedpyright rule flags one. So this is a deliberate pass rather than something the next gate run
announces, which is the whole reason it is filed instead of left to be noticed.

**That paragraph is wrong, and the correction is the useful part.** `reportUnnecessaryCast` is a
basedpyright rule, it is an error under this repo's config, and the first `inv quality.type-check`
after the bump reported **16** of them by file and line — the 14 in `test_init.py`, the one in
`test_cli.py` the plan named, and one in this repo's own `tasks.py` that predates the 0.2.0 pass
entirely and would have been missed by a hand pass working from this plan's list. The gate names
both directions: `reportAny` when a lookup goes loose, `reportUnnecessaryCast` when it stops needing
help.

## Evidence

The casts were added in this repo, commit "Take invoke-stubs 0.2.0, and cast the lookups it made
honest", with the pitfall written into `contributing/type-checking.md`. The finding was filed back
to `invoke-stubs` as its `plans/2026-09-07-consumer-verification-of-0-2-0.md`, whose
`## The decision` section records what shipped and what it beat.

The decision session is `65f8437a-a90e-41c6-9b1f-9b43d713ed9b.jsonl` under
`~/.claude/projects/-home-tdumitrescu-projects-github-com-personal-invoke-stubs/`, 2026-09-07, which
reached the question through "look at any plans we have that fix something" and settled it with the
generic `Lexicon` after rejecting a plain `dict[str, Collection]` declaration — the rejected option
is written up in that plan, not here.

Verified before 0.3.0 shipped, in that repo's integration tier:
`assert_type(ns.collections["sub"],
Collection)` and
`assert_type(ns.tasks["type-check"], Task[Any])` both hold with invoke installed, and putting
`Lexicon[Any]` back reproduced the `reportAny` this repo hit.

## Open questions

Answered 2026-09-07, in the same pass: **rewritten, not deleted.** The instruction to cast went; the
mechanism stayed, now covering all three states that lookup passed through in one day —
`Unknown | None` under 0.1.0, `Any` under 0.2.0, `Collection` under 0.3.0 — plus what the two bumps
together establish, that the gate is loud in a different way at each end. The `is not None` assert
is explained there rather than in a commit message, since it is only explicable next to the union it
was narrowing.

## Recommended direction

1. `uv lock --upgrade-package invoke-stubs`, `inv venv.sync`, then `inv quality.type-check` to
   confirm the gate is still green before touching anything.
2. Remove the 14 casts in `tests/unit/test_init.py` and the matching one in
   `tests/unit/test_cli.py`, and drop the now-unused `cast` import where it becomes one. Re-run the
   gate: `reportAny` is an error in the tests tier, so a lookup this repo got wrong about would fail
   rather than pass silently.
3. Decide the `contributing/type-checking.md` question above in the same pass, while the reason is
   in front of you.

Nothing here is blocked and nothing else in the family is waiting on it. The cost of leaving it is
that the casts read as necessary to the next person, and get copied.

## Migrated to

- [`../contributing/type-checking.md`](../contributing/type-checking.md), the `invoke-stubs` section
  — the three states the same lookup passed through, and the fact that the gate names both
  directions (`reportAny` loose, `reportUnnecessaryCast` tight). That is the whole of what a future
  reader needs; the instruction to cast is gone rather than migrated.
- The commits themselves: "Take invoke-stubs 0.3.0, and drop the 16 casts it made unnecessary" (the
  16th site, in `tasks.py`, that this plan's list did not know about) and "Rewrite the stub pitfall
  around both bumps, not the cast it told you to write".

Not migrated, deliberately: why `Lexicon` is generic rather than a plain `dict[str, Collection]`,
and the option that lost. That is `invoke-stubs`' decision and lives in its
`contributing/stub-decisions.md`; copying it here would ship a second copy that diverges the moment
that repo revisits it.

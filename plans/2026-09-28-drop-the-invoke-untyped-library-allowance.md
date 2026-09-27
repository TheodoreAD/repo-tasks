---
status: landed
updated: 2026-09-28
source_repo: github.com-personal/invoke-stubs
source_session: 76d98521-8e7c-4524-bb4f-4caeb36e8cb0.jsonl
source_moment: 2026-09-28
source_plan: plans/2026-08-30-missing-collection-and-context-stubs.md
---

# The canonical pyrightconfig's `allowedUntypedLibraries: ["invoke"]` is redundant since invoke-stubs 0.2.0

## Context

`src/repo_tasks/configs/pyrightconfig.json` ships `"allowedUntypedLibraries": ["invoke"]`, and every
consumer that pulled it carries it: six personal repos as of 2026-09-28, plus `repo-tasks` itself.
The setting exists because invoke ships no `py.typed`, so before invoke-stubs declared its modules
the checker needed permission to fall back to invoke's inline annotations.

invoke-stubs 0.2.0 shipped a `.pyi` for every module its `__init__.pyi` re-exports from. With those
in place and the setting **removed**, a consumer probing the whole surface (`Collection`, `Config`,
`Context`, `MockContext`, `Result`, `UnexpectedExit`, `Local`, a task's `.body`) type-checked at 0
errors and 0 warnings on basedpyright 1.39.10, invoke 3.0.3. That measurement was the reason
invoke-stubs kept its `py.typed` marker at `partial`. Its rationale is in invoke-stubs'
`contributing/stub-decisions.md`, "Why does `py.typed` still say `partial`?".

Carried as a `DEFERRED` in invoke-stubs' plan from 2026-09-06 until that plan was retired
2026-09-28. It moves here because the canonical config is this repo's, and a consumer that edited
its own copy would just be drift that `configs.diff` reports.

## Evidence

The measurement is in invoke-stubs' retired plan, section 4. Read it back from that repo with
`plans.py archive --show 2026-08-30-missing-collection-and-context-stubs.md`. It was a throwaway
probe in fresh virtualenvs, **not** a run of any consumer's gate. No consumer has had the setting
removed yet.

## Open questions

~~[NEEDS CLARIFICATION:~~ does anything the family imports from invoke fall outside the shipped
modules? `invoke.env`, `invoke.completion`, `invoke.main` and the vendored packages are not declared
by invoke-stubs. Under the `partial` marker they fall back to invoke's inline annotations, and that
fallback may be exactly what `allowedUntypedLibraries` still governs. A
`rg 'from invoke\.' -g '*.py'` across the consumers answers it. If nothing imports those modules,
the setting is dead weight.]

[DECISION: **dead weight, removed 2026-09-28.** A search for invoke submodule imports across every
repo under the personal root finds only `invoke.collection`, `invoke.exceptions` and
`invoke.runners`, in `repo-tasks` and `invoke-stubs`. Every one has a `.pyi` in invoke-stubs. The
only other hits are a vendored copy of invoke's own source in a playground repo, which is not a
consumer. `repo-tasks` locks invoke-stubs 0.3.0, and its gate ran 0 errors and 0 warnings with the
key gone.]

## Migrated to

- `src/repo_tasks/configs/pyrightconfig.json` and this repo's pulled copy: the key is removed.
- `contributing/type-checking.md`, "Where the noise came from": when it was removed, on what
  evidence, and which consumer state is expected to go red when it pulls.

Deliberately not migrated: the probe details, which live in invoke-stubs' own
`contributing/stub-decisions.md`. Reaching the consumers is the normal sweep, and nothing extra is
owed there.

## Recommended direction

Remove the key from the canonical config, run `repo-tasks`' own gate at zero warnings, then let it
reach the consumers through the normal sweep. Each one re-runs its gate with `failOnWarnings` on,
and a consumer still pinned below invoke-stubs 0.2.0 is the one expected to fail.

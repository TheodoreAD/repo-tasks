---
status: idea
updated: 2026-09-29
source_repo: github.com-personal/agent-skills
source_session: c7d58945-4709-4fa6-9253-1140af86d9c0.jsonl
source_moment: 2026-09-29
source_plan: plans/2026-09-13-repo-tasks-consumer-sweep.md
---

# A consumer cannot give one tree its own pyright tier, or check part of a top-level tree

## Context

agent-skills ships 35 Python files under `skills/` that basedpyright has never checked, because the
shipped `include` is `src*`, `tests*`, `tasks*`. The user decided 2026-09-29 to check
`skills/*/scripts` with the `Any`/Unknown rules relaxed for them, the way `tests` has its own
`executionEnvironments` tier, and to leave `skills/*/references/snippets/` out. Two things in
`src/repo_tasks/configs.py` stop that:

1. **No per-consumer rule tier.** `_derive_for_project` resolves only `include` (from
   `[pyright] extra-include`) and `pythonVersion` (from the floor). Everything else is copied
   verbatim, so a consumer's own `executionEnvironments` entry is overwritten by `configs.pull` and
   reported by `configs.diff`.
2. **Top-level granularity only.** `extra-include` appends globs to `include`, and `check-include`
   matches each tracked file's first path segment. So a consumer can check all of `skills/` or none
   of it. `skills*` would take in 21 example snippets that import sqlalchemy, duckdb, pydantic and
   others that are not installed there, and a `skills/*/scripts*` glob, which pyright itself
   accepts, would be reported by `check-include` as never checked.

## Evidence

Measured 2026-09-29, `basedpyright --outputjson skills` under agent-skills' pulled config, on its
3.11 venv: 34 files, 1,202 errors and 931 warnings. About 2,020 are `reportAny` (1,126),
`reportExplicitAny` (214) and `reportUnknown*` (~680): stdlib scripts reading JSON. 23 are
`reportMissingImports`, all in `references/snippets/`. About 50 are real type findings. The
measurement and the user's decision are in agent-skills'
`plans/2026-09-13-repo-tasks-consumer-sweep.md`, section "What v0.5.0 adds".

## Open questions

[NEEDS CLARIFICATION: the shape of the tier. One option is a derived line like `include`: a
`[pyright] relaxed = ["skills/*/scripts"]` key producing an `executionEnvironments` entry with the
`Any`/Unknown rules off. Another is a shipped second tier ("scripts") that any consumer can point
trees at. The first is per-consumer; the second keeps one answer for "which rules are relaxed
where".]

[NEEDS CLARIFICATION: sub-tree include. Either `check-include` learns to evaluate a non-top-level
glob against a file's full path, or an `extra-exclude` key lets a consumer take `skills*` and drop
`skills/*/references`. `include` being top-level by decision (contributing/file-discovery.md) is the
thing either one revisits.]

## Recommended direction

Proposed 2026-09-29 and put to the user, who deferred both questions rather than choosing:

- **Tier shape: a shipped tier, consumer-declared paths.** repo-tasks ships one "scripts" tier with
  the `Any`/Unknown rules relaxed, and a consumer lists which trees get it
  (`[pyright] scripts = ["skills/*/scripts"]`), from which `configs.pull` derives the
  `executionEnvironments` entry. That keeps one answer for which rules are relaxed, and makes the
  paths the declared fact — the same derivation-not-preservation rule `anyio_mode` and
  `pythonVersion` already follow (`contributing/test-tiers.md`, the `anyio_mode` section).
- **Sub-tree include: full-path globs.** `extra-include` accepts a glob like `skills/*/scripts*`,
  which pyright already takes, and `configs.check-include` learns to match a tracked file's full
  path rather than its first segment. That keeps `contributing/file-discovery.md`'s settled
  includes-not-excludes rule, which an `extra-exclude` key would reopen.

Whatever lands, agent-skills then declares its scripts, pulls, and drops `skills*` from its
`[pyright] unchecked`. Its ~50 real findings are already fixed there (agent-skills `4a723bb`, not
yet pushed on 2026-09-29), so declaring the tier should turn its gate on with nothing red.

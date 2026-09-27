---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/invoke-stubs
source_session: 76d98521-8e7c-4524-bb4f-4caeb36e8cb0.jsonl
source_moment: 2026-09-28
source_plan:
---

# `deps.check-currency` reports every behind entry as "not in this project's dev group" when color is forced

## Context

Found running the v0.5.0 consumer sweep in `invoke-stubs`, with this repo pinned at `v0.5.0`
(`023363c4`). The check exits 0 and reads as a clean bill of health, so the failure is silent. A
sweep that trusted it would have left five tools behind.

## Evidence

Run from a Claude Code Bash call. The harness exports `FORCE_COLOR=3`, and no dotfile on this
machine sets it:

```
[deps.check-currency] basedpyright  not in this project's dev group — `inv configs.diff` reports that
[deps.check-currency] ruff  not in this project's dev group — `inv configs.diff` reports that
... (shfmt-py, actionlint-py, zizmor, hadolint-py the same)
[deps.check-currency] 0 of 13 manifest entries behind
```

All six are declared in the dev group, and `configs.ensure-deps` in the same shell said "already
present" for each. They are exactly the six that were behind. The raw
`uv tree --outdated --depth 1 --locked --only-group dev --quiet` output from that shell shows why:

```
├── basedpyright v1.39.10 (group: dev) \e[36m\e[1m(latest: v1.40.1)\e[0m\e[39m
```

uv honours `FORCE_COLOR` even when stdout is a pipe, so the `(latest: …)` clause arrives wrapped in
ANSI escapes. `_TREE_LINE_RE` in `src/repo_tasks/deps.py` anchors on `$` after an optional plain
`(latest: v…)`, so the line fails to match at all. The name never enters `tree`, and the loop
reports it as undeclared. Current lines have no colored clause, so they match, and the result is
that exactly the behind entries vanish.

The same command with `env -u FORCE_COLOR` gives the right answer: basedpyright and the other four
current after the upgrade, and `hadolint-py` behind.

## A second, smaller finding from the same run

`hadolint-py 2.14.0.1 BEHIND — latest 2.15.1.2`, with next step
`inv deps.lock --package hadolint-py`. But `invoke-stubs`' dev group declares
`"hadolint-py!=2.15.1.2"`, so that version is excluded on purpose, and the suggested command cannot
move to it. `uv tree --outdated` reports the index's latest, not the latest the specifier admits.

**Already covered** by `plans/2026-09-28-check-currency-ignores-the-manifest-constraint.md`, filed
by a parallel session the same night and already absorbed. That is the same finding. This section is
one more instance of it, and the clarification below belongs there, not here.

## Recommended direction

Add `--color never` to `_CURRENCY_TREE_CMD`, which is the smallest fix and covers `NO_COLOR`,
`FORCE_COLOR` and `CLICOLOR_FORCE` alike. Add a unit test feeding the regex a colored line, and show
it failing before the fix. Then grep the package for any other `c.run(...)` whose stdout is parsed
by regex. The same environment breaks those too.

[NEEDS CLARIFICATION: for the second finding, report an excluded latest as "latest excluded by your
specifier" rather than BEHIND, or leave it and let the reader notice? It is the consumer's
deliberate choice either way, and a check that nags about a deliberate exclusion gets ignored.]

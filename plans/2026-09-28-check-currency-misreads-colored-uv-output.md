---
status: landed
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

**Already covered** by the now-retired
`plans/2026-09-28-check-currency-ignores-the-manifest-constraint.md`, which landed as `08f17fe`:
each flagged entry is confirmed with a dry-run lock upgrade, and an excluded latest is reported as
`current — latest X is excluded by this project's constraints`.

## Recommended direction

Add `--color never` to `_CURRENCY_TREE_CMD`, which is the smallest fix and covers `NO_COLOR`,
`FORCE_COLOR` and `CLICOLOR_FORCE` alike. Add a unit test feeding the regex a colored line, and show
it failing before the fix. Then grep the package for any other `c.run(...)` whose stdout is parsed
by regex. The same environment breaks those too.

~~[NEEDS CLARIFICATION:~~ for the second finding, report an excluded latest as "latest excluded by
your specifier" rather than BEHIND, or leave it and let the reader notice? It is the consumer's
deliberate choice either way, and a check that nags about a deliberate exclusion gets ignored.]

Answered by the user's decision on the retired constraint plan: report it as excluded, not BEHIND.
That landed in `08f17fe`.

Landed in `6883908`. It went wider than the direction above, because the sweep it asked for found
two more parsers the same environment breaks:

- `selfinstall._installed_tools` parses `uv tool list`. Under `FORCE_COLOR` a bold escape precedes
  every tool name, the first-character test fails, and every tool reads as absent.
- `ci.status` parses `gh run list --json` and the annotations `gh api` call. gh ignores
  `FORCE_COLOR` but colours JSON under `CLICOLOR_FORCE`, and `json.loads` then crashes. Neither
  `NO_COLOR` nor `--jq .` stops it on gh 2.101.0; `CLICOLOR_FORCE=0` does.

The direction's claim that `--color never` covers `NO_COLOR`, `FORCE_COLOR` and `CLICOLOR_FORCE`
alike holds for uv only, which is why gh gets its own switch. The unit-test shape also changed: the
fix turns colour off at the source, so the tests pin the flags rather than feed a coloured line to a
regex that never sees one. The end-to-end check was running the three tasks under
`FORCE_COLOR=3 CLICOLOR_FORCE=1`, wrong or crashing before and correct after. `--jq` calls returning
scalars, and every git call, were checked and need nothing.

## Migrated to

- `src/repo_tasks/deps.py`, `selfinstall.py` and `ci.py`: a comment at each constant or call says
  why output is forced plain, and for gh which switch works.
- `tests/unit/test_deps.py`, `test_selfinstall.py` and `test_ci.py`: the pins.

Deliberately not migrated: the invoke-stubs sweep narrative, since the commit message carries the
reproduction.

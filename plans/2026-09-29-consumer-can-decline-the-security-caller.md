---
status: idea
updated: 2026-09-29
source_repo: github.com-personal/agent-skills
source_session: c7d58945-4709-4fa6-9253-1140af86d9c0.jsonl
source_moment: 2026-09-29
source_plan: plans/2026-09-13-repo-tasks-consumer-sweep.md
---

# `consumers.diff` reports a missing security caller that a consumer declined on purpose

## Context

Since 2026-09-26, `inv consumers.diff` reports a consumer with no `security.yml` calling
`security-reusable.yml`. agent-skills decided 2026-09-29 not to add one: its `pyproject.toml` has
`dependencies = []` and `package = false`, so nothing in its `uv.lock` ships to anyone who installs
its skills. All 21 audited packages are dev tooling, the shipped scripts run on an ambient
interpreter's stdlib, and a green Security check would imply coverage of what consumers run that it
does not have.

There is no way to record that, so every sweep will report it again and someone will have to
remember why it is fine.

## Evidence

The decision and its reasoning are in agent-skills' `plans/2026-09-13-repo-tasks-consumer-sweep.md`,
under "What no diff can tell you", the security workflow item. `uv audit --locked` there, the same
day: no known vulnerabilities in 21 packages.

## Recommended direction

A declaration in the consumer's own `repo-tasks.toml`, the same shape as `[pyright] unchecked`: for
example `[security] caller = false` with a required `reason`. `consumers.diff` then prints it as
declined, with the reason, rather than as missing, and still reports a caller whose SHA is behind
for consumers that have one. `[pyright] unchecked` is the precedent: a deliberate gap is reported as
deliberate rather than failing.

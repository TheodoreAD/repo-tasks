---
status: idea
updated: 2026-09-08
---

# Per-step log files, as a second axis beside report mode

## Context

Carried out of the retired `plans/2026-09-05-run-reporting-as-an-opt-in-agent-mode.md`, whose §7
designed this and deferred it. It is the only part of that plan that was neither built nor handed to
another repo, so it moves here rather than being lost with the file.

The shape, unchanged from that design: `REPO_TASKS_RUN_LOG_DIR=<dir>` makes the reporting runner
write each reported step's output to `NNN-<slug>.log` and append `| log=<path>` to the report line.
On failure the inline replay becomes a bounded tail plus the path instead of the whole output.

Each log is written with an explicit `encoding="utf-8"` rather than letting the console codepage
decide — the same rule the rest of this package already follows for every file read and write.

**It is a genuinely separate axis from report mode**, which is why it was designed as its own
variable rather than as a mode flag: report mode decides what reaches the terminal, and this decides
what is additionally kept. Either is useful without the other.

## Why it was deferred rather than built

[DECISION: build it only when there is a reason, from the retiring plan. The problem that motivated
it in the project the design was borrowed from was Windows — PowerShell and UTF-8 disagreeing — and
this family is Linux, so that half does not apply here (see
[`2026-09-06-windows-support.md`](2026-09-06-windows-support.md), which settles that Windows is not
a target). What survives is context economy on a failing step, and that argument is the weakest one
available for this feature: a failure is the single moment an agent actually wants the output
inline, which is exactly what report mode already does.]

## Open questions

[NEEDS CLARIFICATION: what would count as the reason to build it? The honest candidates are a gate
step whose failure output is genuinely too large to replay inline — nothing in the current gate is
close — or a consumer running the gate somewhere the terminal output is not kept at all. Neither has
appeared. Worth deciding whether this plan should simply be abandoned if a year passes without one,
rather than sitting as a permanent idea.]

[NEEDS CLARIFICATION: does CI change the answer? The gate runs stock invoke in CI by decision, so
report mode is off there and this axis would be too — but CI is the one place where per-step logs
could become artifacts. That is a different feature with a different trigger, and folding it in here
would be answering a question nobody has asked.]

## Recommended direction

Leave it as an idea. The design above is complete enough to build from if a reason appears, and
nothing about it decays — it depends only on the runner's own interface, which is this package's.

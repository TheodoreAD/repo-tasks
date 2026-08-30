---
status: idea
updated: 2026-08-30
---

# Checks nobody's commit runs

## Context

Three separate pieces of this repo share one shape: they answer a question whose answer changes
without any code changing, so they are correctly outside `quality.check`
([`../contributing/quality-gate.md`](../contributing/quality-gate.md)) — and nothing then runs them
on a cadence, so each can sit stale or red indefinitely with a green terminal everywhere.

They arrived from three different plans and were each deferred separately. Collected here because
the trade-off is the same one and should be settled once rather than three times.

1. **`deps.audit` in CI.** Designed to run on push to `main` only, no schedule, by explicit decision
   at the time — the user's call, deliberately not starting a cadence. The uncovered case is an
   advisory landing during a week with no pushes. `ci.status` was the stated mitigation. (Separately
   blocked on [`2026-08-24-devpi-dependency-weight.md`](2026-08-24-devpi-dependency-weight.md),
   which is about whether the step can be added at all, not about how often it runs.)
2. **The integration tier.** Opt-in and run by nobody's commit, which
   [`../contributing/test-tiers.md`](../contributing/test-tiers.md) states as a deliberate design
   choice rather than an oversight. It sat red for an unknown length of time on a fixture handing
   `version.py` an invalid version string, and while it was red it hid a second, unrelated failure
   behind it.
3. **`ci.check-actions` and `ci.status`.** Both need someone to type them; see
   [`2026-08-28-node20-action-deprecation.md`](2026-08-28-node20-action-deprecation.md), which
   raised the same trade-off and asked for it to be settled once for all of these. `ci.status` is at
   least already part of a habit — it is the pre-push check — so the currency half is the weaker of
   the two.

## Open questions

[NEEDS CLARIFICATION: is the answer one scheduled workflow or several? A single weekly job running
`deps.audit`, `ci.check-actions` and the integration tier is one place to look and one notification
to ignore; three separate schedules fail independently and say which thing went stale. The failure
mode of any of them is the same, though — a scheduled job that fails on a repo nobody watches is
exactly the silence `ci.status` exists to break.]

[NEEDS CLARIFICATION: does the integration tier even run in CI? It needs a Docker daemon and pulls
`registry:3` and a Debian base image. GitHub-hosted runners can do it, but it is the first thing in
this family to need a daemon in CI, and the cost is not measured.]

[NEEDS CLARIFICATION: who reads the result? The repo pushes straight to `main` and reviews no PRs,
so a red scheduled run has no natural reader. Either this comes with a notification path that
actually reaches the user, or it is `ci.status` plus a habit — and if it is the latter, the honest
answer may be that no schedule is wanted and the three items above are simply accepted risks.]

[NEEDS CLARIFICATION: this is a repo-tasks question, but every consumer inherits the same shape
through `scaffoldapy`'s workflow templates. Whether the answer ships or stays local is part of the
decision.]

## Recommended direction

Settle the "who reads it" question first — it decides the other three. If there is a notification
path, one weekly workflow calling all three is the cheap version and can start with the two that
need no daemon. If there is not, close this by recording the accepted risk in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md) rather than leaving three
deferred items pointing at each other.

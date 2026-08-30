---
status: idea
updated: 2026-08-30
---

# The push-triggered `deps.audit` step, now that nothing blocks it

## Context

Designed by the 2026-08-26 quality-gate coverage sweep and the one part of it that never landed:
`inv deps.audit` running in CI on push to `main`. It could not be added, because it would have been
red from its first run — `devpi-server`'s `setuptools<=81` (and its `pyramid` dependency's `<82`)
held this repo's lock on a `setuptools` carrying two advisories that nothing here could fix. The
deferral was recorded against the devpi plan rather than worked around, precisely so no suppression
list or narrowed CI scope would bake that pin into shipped code.

**That blocker is gone as of 2026-08-30.** devpi was replaced by pypiserver plus a JSON stub
([`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Package index"), which took the
lock from 98 packages to 63, removed `setuptools` from it entirely, and took `inv deps.audit` to
`Found no known vulnerabilities`. Nothing stands in the way of the step now except writing it.

The task itself already exists and is already correct — `deps.audit` is `uv audit --locked`, marked
`@requires(NETWORK)`, standalone by rule 1 because its answer changes when the OSV database changes
rather than when the code does
([`../contributing/quality-gate.md`](../contributing/quality-gate.md)). This plan is only about
where and when CI runs it.

## Open questions

[NEEDS CLARIFICATION: which workflow? A step appended to `ci.yml` runs it on every push including
feature branches, which is more often than the concern warrants and puts a network call in the
every-commit workflow that `quality.check` deliberately keeps offline. Its own small workflow
triggered on push to `main` keeps that separation intact at the cost of a second file. The second
looks right, but it has not been weighed against how noisy the first would actually be.]

[NEEDS CLARIFICATION: what happens when it goes red? An advisory can land on a transitive with no
fixed version available, which is exactly the state this repo was in for four days — and the
no-suppression decision means the task stops loudly with no way to acknowledge and move on. On a
repo that pushes straight to `main` that turns every such advisory into a red `main` until someone
acts. That is arguably correct and is certainly the decision already taken, but the CI step is what
makes it visible, so it is worth confirming rather than discovering.]

[NEEDS CLARIFICATION: does this ship to consumers? `deps.audit` reaches every consumer through
`repo-tasks-quality`, and `scaffoldapy` generates the workflows. A generated repo inheriting a
push-triggered audit inherits the red-`main` behaviour above along with it, without having chosen
the no-suppression stance. Same shape as the question in
[`2026-08-30-scheduled-checks-cadence.md`](2026-08-30-scheduled-checks-cadence.md), and probably
wants the same answer.]

## Recommended direction

Its own workflow on push to `main`, not a step in `ci.yml` — the gate's offline guarantee is worth
more than the second file costs, and a `@requires(NETWORK)` task sitting inside the every-commit
workflow invites exactly the drift rule 1 exists to prevent.

Keep it local first. The consumer question above is real, and shipping a workflow that can redden a
generated repo's `main` over an unfixable transitive is not something to do by default before this
repo has lived with it for a while.

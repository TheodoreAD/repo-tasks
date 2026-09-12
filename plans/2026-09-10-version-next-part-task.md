---
status: idea
updated: 2026-09-10
---

# A task that computes the bump part instead of asking someone to remember the rule

## Context

Carried out of `2026-09-04-versioning-policy.md` when that plan was retired on 2026-09-10; the rule
it defended is settled and lives in
[`../contributing/versioning.md`](../contributing/versioning.md), "What minor and patch mean here".

That rule is deliberately mechanical — **minor means a surface in the enumerated list moved, patch
means it did not** — and the whole reason it is phrased that way is so a task can answer it. Today
the answer comes from a person diffing the surface by hand and passing `--bump minor` to
`inv trunkflow.cut`. `inv version.next-part --since v0.2.0` would diff the paths that
`versioning.md` enumerates and print `minor` or `patch`.

It is the kind of thing this package exists to hand other repos: the rule is family-wide, the
surface list is already written down, and every consumer that cuts a release faces the same
question. What makes it worth building is also what makes it worth delaying — the surface list is
the input, and a task reading a stale list is a rule that reports "patch" for a release that
rewrites a file in every consumer repo.

## Open questions

[NEEDS CLARIFICATION: where does the surface list live once a task reads it? Today it is prose in
`versioning.md`, audited by hand. A task needs it as data — a constant in `version.py`, with the
doc's list generated from it. **The mechanism for that half now exists**: `inv docs.generate`
renders a block from this package's own code into a marked region and `inv docs.generate-check`
fails the gate when it drifts, which is how `README.md`'s task-requirements table is kept honest
([`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Generation runs first"). So
the open part is only where the constant lives and what shape it takes, not how the doc follows it.
Prose and code drifting apart is the failure that matters here, because the drift is silent and the
answer stays plausible.]

[NEEDS CLARIFICATION: what does it do about a surface entry that is a contract rather than a path —
"module names are API", "`configure` staying unnested", the `repo-tasks.toml` schema? A path diff
sees a renamed module; it does not see a task's signature changing. Either the task reports only the
half it can measure and says so, or those contracts need a mechanical form too.]

[NEEDS CLARIFICATION: is `--since <tag>` the right interface, or should it default to the last tag
reachable from `HEAD`? The default is what makes it usable inside `trunkflow.cut`; the explicit form
is what makes it auditable after the fact.]

## Recommended direction

Rough, and deliberately not started. **The evidence so far argues against building it, not for.**
The rule has been applied twice for real — `v0.2.0` and `v0.3.0` (2026-09-08) — and both times it
took under a minute and returned an unambiguous answer. A task automating a step that costs a minute
and never goes wrong is a maintenance surface bought with nothing.

1. **Keep counting rather than building.** Each release is free evidence: record whether the hand
   answer needed judgement. If one ever does, that exception is the design's real requirement and
   the case reopens; if several more do not, this plan should be abandoned rather than left open.
2. **Make the surface list data before making it a task.** Whatever reads it — a report, a task, a
   gate step — is downstream of that, and the doc-generation plan above is where the mechanism
   belongs.
3. **Report, do not bump.** Printing the part leaves the decision where it is now; wiring it into
   `trunkflow.cut --bump auto` is a separate decision with a different failure mode, and the same
   detector-over-editor argument that settled `ci.check-actions` applies
   ([`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Workflow hardening").

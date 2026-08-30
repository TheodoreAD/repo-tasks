---
status: idea
updated: 2026-08-30
---

# Gate candidates offered during the coverage sweep and not taken

## Context

The 2026-08-26 sweep asked which classes of problem `quality.check` did not look for at all, and
adopted a tool for each concern that earned one — the result is
[`../contributing/quality-gate.md`](../contributing/quality-gate.md). Two candidates were evaluated,
found genuinely useful, and still not adopted. Both are recorded here rather than in that file
because they are wanted, not rejected: what is written there is the settled half.

### deptry

Run ad hoc during the sweep and it earned its keep immediately. Adopting it means a permanent
dependency in every consumer plus per-repo false-positive configuration, which the shipped-config
model has nowhere to put. Re-run by hand when dependencies change.

What it found, so the next run is not a surprise:

- `bump-my-version` and `repo_tasks` (twice — the dogfooding self-import) are false positives:
  shelled out, and self-referential, respectively.
- `python-dotenv` is reported unused and genuinely is (`rg dotenv` over `src/`, `tests/`, `tasks.py`
  returns nothing). It stays: a deliberate forward-looking dependency for local `.env`-based
  configuration of task options. **Not a defect, and not to be "cleaned up" by a future pass.**

[PITFALL: deptry does not check dependency groups for unused entries at all, so it would never have
caught a stale `repo-tasks-quality` entry — which is the thing that motivated looking at it in the
first place.]

### ruff `S602` / `S603` / `S607`

The non-noise slice of bandit, relevant precisely because shelling out is what this package does.
Offered during the sweep and not taken; the whole `S` family stays correctly rejected as noise, and
this is the argument for carving three rules out of that rejection rather than reversing it.

## Open questions

[NEEDS CLARIFICATION: deptry's per-repo config problem may not be real. Its ignores go in
`pyproject.toml`, which is per-repo by nature and not a shipped config at all — the shipped-config
model has nowhere to put them because it does not need to. What that leaves is a per-consumer
maintenance cost rather than a mechanism gap, which is a smaller objection than the one recorded at
the time.]

[NEEDS CLARIFICATION: if deptry is adopted, is it a gate step or standalone? It is offline and
deterministic, so rule 1 admits it — but its false-positive rate is what decides whether a consumer
can be handed it as a gate step on day one.]

[NEEDS CLARIFICATION: `S603` in particular flags every `subprocess` call without a check, which in
this package is close to every task. Whether the three rules produce findings or a wall of `noqa`
has not been measured — run them once against `src/` before deciding.]

## Recommended direction

Measure before deciding either: one `deptry` run and one `ruff --select S602,S603,S607` run against
this repo produce the numbers both questions turn on, and neither costs more than a few minutes.
Adopt into the gate only what comes back with a finding rate a consumer would tolerate.

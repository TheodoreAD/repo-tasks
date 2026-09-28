---
status: idea
updated: 2026-09-06
---

# Should `configs.diff`'s dev-group half run inside `quality.check`?

## Context

Left open deliberately by the 2026-09-06 machine-particularities audit, which fixed the three
findings around it and stopped here because this one is a design decision rather than a defect.

The audit established that **the machine where this package is written cannot see the drift the gate
exists to catch**. With the project venv taken off `PATH`, four of the eight gate binaries —
`dprint`, `shellcheck`, `shfmt`, `actionlint` — still resolve from `~/.local/bin`, installed there
machine-wide by a sibling repo. So `configs.require_tool` returns early for those four however stale
a consumer's `dependency-groups.dev` is, and `actionlint` is the tool whose missing entry caused the
2026-08-24 incident the preflight was written for.

What landed instead, because it changes no verdict:

- `require_tool` now **warns** when a binary resolves from outside the project, naming where it came
  from and that CI will fail (`configs._warn_if_undeclared`).
- `configs.diff` gained the constraint half, so a manifest entry a consumer declares _without_ the
  manifest's version constraint is reported (`configs._unconstrained_quality_deps`).

Neither runs in the gate. `_CHECKS` carries `deps_check` (lock drift) and not `configs.diff`, so a
consumer's dev group falling behind the manifest still surfaces first in **their** CI, hours later —
which is exactly the incident shape.

## The trade

[NEEDS CLARIFICATION: **the gate's determinism contract is the real objection, and it is not
rhetorical.** `quality.check`'s docstring promises every step is deterministic — "safe to run
concurrently, on a read-only checkout, and twice with the same answer". `configs.diff` reads the
**installed** `repo_tasks` package, so its answer moves when `inv repo-tasks.update` runs and the
same commit gates differently before and after. Every other step depends only on the working tree.
Putting it in the gate would be the first step whose verdict depends on something outside the
checkout.]

[NEEDS CLARIFICATION: **and it would flip a large number of consumers red at once, correctly.**
Every consumer whose group is behind is genuinely broken — their CI will fail on the next manifest
addition — so failing locally is failing at the right moment. But it is a default change with
family-wide blast radius, which is the shape `~/AGENTS.md` says to make opt-in rather than to move
under everyone. A `--strict` flag, or gating only `precommit` and not `check`, are both cheaper
positions worth pricing first.]

[NEEDS CLARIFICATION: is the warning enough? It was chosen because it makes the state visible where
it is created without changing a verdict, and nothing yet says whether a warning in a fifteen-line
report gets read. The honest test is the next manifest addition: if a consumer still goes red in CI
having been warned locally first, the warning is not enough and this question answers itself.]

## Recommended direction

Wait for that test rather than deciding now. The next family-wide manifest change is the natural
trigger, and it is also what answers the `[UNVERIFIED:]` below, moved here 2026-09-26 when the
now-retired `2026-08-25-consumer-transitions.md` was retired — the two questions want the same
event, so they are read together.

[UNVERIFIED: **`configs.require_tool`'s preflight has never fired from a consumer's own CI**, only
locally (landed `99f26a8`, 2026-08-26). Every consumer sweep since — `power-user-linux-setup` twice,
`ingesta` once — moved only non-binary items, so none could make it fire, and the canary cannot
either: it pulls no config and reads no dev group. It waits on a family-wide manifest change that
adds a **gate binary**. When one lands, note which consumer's CI printed the preflight message
rather than exit 127 — and, per the third question above, whether that consumer had been warned
locally first.]

If it does move, prefer `precommit` over `check`: `precommit` is already the half that may mutate
and the one a human runs deliberately, so a step whose answer depends on the installed package is
less of a contradiction there than in the read-only half CI runs.

## The config-files half of the same question

[DEFERRED: **whether a local edit to a pulled config file should surface in the routine gate.**
`configs.diff` already compares every pulled file with the canonical copy, and nothing in
`quality.precommit` runs it, so a hand-edited file stays diverged silently until someone runs the
`configs.pull` that reverts it. Found 2026-08-29 when a consumer hand-added `anyio_mode = auto` to
its `pytest.ini`: derivation removed that case — the line is now computed from the consumer's own
lock — but not the general hole, which the next hand-edit falls into. It is this plan's question
applied to the other half of `configs.diff`, with the same determinism objection, since the
canonical copy is read from the installed package. Moved here 2026-09-29 from the retired
`plans/2026-08-29-pytest-ini-anyio-mode.md`.]

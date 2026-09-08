---
status: idea
updated: 2026-09-08
---

# Detect a tracked Python tree no pyright `include` entry covers

## Context

The shipped `pyrightconfig.json` is include-shaped by decision
([`../contributing/file-discovery.md`](../contributing/file-discovery.md), "The rule: includes, not
excludes"): `include: ["src*", "tests*", "tasks*"]`, and basedpyright is blind to `.gitignore`, so
the include list is the only thing deciding what gets type-checked. The cost of an include list is
the mirror of an exclude list's: a new top-level directory is simply never checked, and nothing says
so. `examples/sample-service` sat in exactly that gap until it moved under `tests/fixtures/`, found
by accident rather than by the gate.

Carried out of the now-retired `plans/2026-08-19-gitignore-tool-alignment.md`, which paired this
with a `git check-ignore` check for `.venv`; that half was dropped on measurement (the venv ignores
itself, see the same doc), and this half is the only live question it left.

## The second instance exists, measured 2026-09-08

The plan's own gate was "wait for a second instance before building anything". One exists, and it
was found by implementing the proposed test rather than by noticing it: `fnmatch` of each tracked
`*.py`'s first path segment against the repo's own `include` entries, run read-only against all
three repos in the family.

| repo                     | tracked `*.py` | uncovered                 |
| ------------------------ | -------------- | ------------------------- |
| `repo-tasks`             | 71             | none                      |
| `power-user-linux-setup` | 68             | none                      |
| `scaffoldapy`            | 12             | **`template/`** — 2 files |

`template/tasks.py` and `template/tests/conftest.py`, both literal Python rather than Jinja, neither
seen by basedpyright in any run since the file was written.

**That answers the second open question below outright.** The first-segment `fnmatch` test is not
merely cheap in theory — it is written, it runs against a real corpus, and it found the case it was
designed for on the first try. Nothing about "what matched means mechanically" is still open.

### The counter-argument is not realised by it, and a stronger one replaces it

The objection recorded below is that a consumer with a deliberately untyped tree would be **red on
correct input**. Measured against the one real instance, that does not happen: basedpyright over
those two files under `scaffoldapy`'s own config reports **0 errors, 0 warnings, 0 notes**. Adding
`template*` to that repo's `include` would be green, not red — the fear was reasonable and the
evidence does not support it.

[PITFALL: **`template/tasks.py` passes because it already carries the suppressions it needs**
(`# pyright: ignore[reportMissingImports, reportUnknownVariableType]`, for an import that resolves
only through the global `uv tool` install). Nothing has ever exercised them, because nothing checks
the file — so the file is green today by a correctness nobody has verified, and would stay green by
coincidence if the suppressions later became wrong. An unchecked file's ignore comments are not
evidence that the ignores are right.]

[DECISION: **the real objection is that the consumer cannot act on the finding**, and it is the one
that should decide this rather than the red-on-correct-input worry. `include` is shipped
**verbatim** — `["src*", "tests*", "tasks*"]` in the packaged `pyrightconfig.json` — and
`configs.pull` derives exactly two lines per consumer, `pythonVersion` and `anyio_mode`
(`configs._derive_for_project`). `include` is neither of them. So a consumer told "your `template/`
tree is unchecked" has no supported remedy: editing its own `pyrightconfig.json` is reverted by the
next `configs.pull`, which is the mechanism the sweep runs routinely. A check that reports a true
finding with no available fix is worse than no check, whichever of gate-step or diagnostic it is
spelled as.]

## Open questions

[NEEDS CLARIFICATION: is it worth a gate step, or a diagnostic? A check that every tracked `*.py`
(`tracked_files(c, "*.py")`) is matched by some `include` entry would catch a new tree the moment it
appears. Against: one instance ever, and a consumer with a deliberate untyped tree (a `scripts/` of
throwaway one-offs, a vendored directory) would be red on correct input with no opt-out short of
editing a config `configs.pull` overwrites. That argues for a `quality.*-check`-shaped diagnostic
that is not in `check`'s chain, or for the check reporting rather than failing.

**Still open, but on different premises than when it was written** — see the 2026-09-08 measurement
above. "One instance ever" is now two. "Red on correct input" is measured and does not happen on the
real one. What survives, and is the reason this stays open rather than resolving, is the last
clause: the absence of an opt-out. That has gone from a side-condition to the deciding factor.]

[DECISION: **"matched by an include entry" is `fnmatch` on the file's first path segment**, settled
2026-09-08 by writing it and running it against all three repos rather than by argument. The shipped
entries are top-level-anchored globs (`src*`), so no walk is needed; the implementation is a dozen
lines and it found `scaffoldapy`'s `template/` immediately.

One detail in the original wording is **wrong and worth correcting rather than deleting**: it said
the check must read the consumer's own `pyrightconfig.json` rather than the packaged copy "since the
two can differ by exactly the entries a consumer added". Reading the consumer's own file is right,
but not for that reason — a consumer _cannot_ add entries that survive, because `configs.pull`
rewrites the file and derives only `pythonVersion` and `anyio_mode`. The two differ by a consumer's
**pending drift**, not by its deliberate additions, and that difference is the whole problem above.]

## Recommended direction

~~Wait for a second instance before building anything.~~ One arrived, 2026-09-08, and it moved the
question rather than answering it: the detector works and the finding is real, but the consumer it
fires on has no supported way to act on it.

**So the order is now the reverse of what this plan assumed.** Make `include` extensible before
building anything that reports on it — otherwise the first thing `quality.include-check` does is
tell `scaffoldapy` about a tree it cannot cover. Two shapes, and neither has been priced:

1. **Derive `include` per consumer**, the way `pythonVersion` and `anyio_mode` already are — from
   what the repo actually has on disk, or from a key it declares. Fits the existing mechanism
   exactly, and `configs._derive_for_project` is where it would go.
2. **Let a consumer declare extra trees** in `repo-tasks.toml`, which `configs.pull` splices in. A
   new kind of key for that file, but the honest one if the answer is "this is the consumer's
   choice, not something derivable".

Only once one of those exists does the check have a remedy to name, and at that point the gate-step
question above is much easier: a check whose finding is fixable in one declared line is a very
different proposition from one whose finding is a dead end.

**Do not build the check first on the strength of the second instance.** That instance is evidence
the detector is worth having, not evidence it is currently useful.

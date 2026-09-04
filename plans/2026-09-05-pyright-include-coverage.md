---
status: idea
updated: 2026-09-05
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

## Open questions

[NEEDS CLARIFICATION: is it worth a gate step, or a diagnostic? A check that every tracked `*.py`
(`tracked_files(c, "*.py")`) is matched by some `include` entry would catch a new tree the moment it
appears. Against: one instance ever, and a consumer with a deliberate untyped tree (a `scripts/` of
throwaway one-offs, a vendored directory) would be red on correct input with no opt-out short of
editing a config `configs.pull` overwrites. That argues for a `quality.*-check`-shaped diagnostic
that is not in `check`'s chain, or for the check reporting rather than failing.]

[NEEDS CLARIFICATION: what "matched by an include entry" means mechanically. The shipped entries are
top-level-anchored globs (`src*`), so the test is "the file's first path segment matches one of the
globs" — `fnmatch` on the first segment, not a walk. Cheap, but it has to read the consumer's own
`pyrightconfig.json` rather than the packaged copy, since the two can differ by exactly the entries
a consumer added.]

## Recommended direction

Wait for a second instance before building anything. If one arrives, the narrow shape is a
`quality.include-check` that lists uncovered top-level trees and exits non-zero, kept out of
`check`'s chain until a consumer has asked for it — the family convention is that the shared
composite is mandatory and identical, so a step that can be red on a deliberate layout must earn its
place with evidence rather than with the one case that motivated it.

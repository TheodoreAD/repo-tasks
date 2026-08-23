---
status: idea
updated: 2026-08-23
---

## Context

[`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)'s "No-op
cleanly when an artifact kind is absent" says a task acting on an artifact kind the repo doesn't
have should print a short note and return, so it is safe to wire unconditionally into a composite
with no per-repo opt-out. `quality.shell_check` and every task in `helm.py` follow it.

`docker.py` does not. `_resolve_image` raises `ValueError("no docker image found ...")` when a repo
has no `[[docker]]` entries and no root `Dockerfile` — it predates the convention being written
down. Carried over from the now-retired `plans/2026-08-19-helm-chart-tasks.md`, whose §2 flagged it
while landing `helm.py` in the stricter shape.

Tolerable while nothing wires `docker.*` into a composite: today a consumer only ever reaches those
tasks by naming them, and an error is a reasonable answer to "build the image" in a repo with no
image. It becomes a real problem the moment a top-level release composite exists, which is the
trigger to do this rather than a date.

## Recommended direction

Align `docker.py`'s `build`/`push`/`release` with `helm.py`'s print-and-return shape, keeping the
half of the current behaviour that is already right: an explicit `--project` naming nothing stays an
error, since that is ambiguity rather than absence.

[NEEDS CLARIFICATION: does `release` no-op as a unit, or is a repo with no image but a `--project`
argument a different case worth distinguishing? `helm.py` has only the simple case so far, so there
is no precedent to copy.]

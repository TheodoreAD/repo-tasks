---
status: idea
updated: 2026-08-26
depends_on: [invoke-stubs]
---

# Two loose ends from the type-checking rollout

Both carried over from the now-retired `plans/2026-08-25-type-check-warning-noise.md`, whose settled
content lives in [`contributing/type-checking.md`](../contributing/type-checking.md). Neither blocks
anything; both are small and both would delete code if they land.

## Context

The rollout got both repos to zero warnings with `failOnWarnings: true` family-wide. Two things were
consciously scoped out at the time and are still true as of 2026-08-26.

## Open questions

- [DEFERRED: offer the `@task` signature upstream to pyinvoke — the stub's `ParamSpec` overloads for
  `task()` plus an `__all__` (or `import X as X` re-exports) in `invoke/__init__.py`. invoke's
  `main` is unchanged as of 2026-08-25. If a released invoke ever carries it, `invoke-stubs` is
  deleted outright and the `repo-tasks-quality` entry with it — which is the whole reason it is
  worth offering rather than maintaining a stub indefinitely. `invoke-stubs` is one commit old
  (`ad052ca`), so there is no divergence to reconcile yet.]

[NEEDS CLARIFICATION: is an upstream PR actually wanted, given it means owning a contribution
against a project that has not moved on this? The cheap middle option is opening an issue with the
stub as the proposed shape and letting the maintainers decide, rather than a PR that may sit.]

- [DEFERRED: a `task(klass=..., **kwargs)` overload in `invoke-stubs`. invoke's own extension point
  for task metadata is a `Task` subclass plus custom keywords, and the stub types `klass` but has no
  overload accepting the extra keywords that subclass exists to receive — so
  `@task(klass=Custom,
  thing=...)` matches nothing, `@task` degrades to an untyped decorator, and
  the decorated function's `.body` becomes `Any` with `reportUntypedFunctionDecorator` firing.
  Measured 2026-08-26 while designing `requirements.py`, which routed around it with a
  separately-typed decorator instead (see `contributing/task-module-conventions.md`). Nothing needs
  the stub change today; it is recorded because it is the second real gap found in the stub, which
  is this plan's own stated trigger for revisiting the upstream question.]

- [DEFERRED: the `sample-service` fixture's `reportImplicitOverride`. `typing.override` is 3.12+ and
  the fixture declares `requires-python = ">=3.11"` with no dependencies, so it currently carries a
  line-level `# pyright: ignore[reportImplicitOverride]` with a comment saying why
  (`tests/fixtures/sample-service/src/sample_service/__main__.py`). Either raise the fixture's floor
  to 3.12 and use `@override`, or keep the one line. Not worth an `exclude` — the shipped config's
  own comment explains why an exclude list is the wrong shape.]

## Recommended direction

Leave both. The `override` one is a single suppressed line with its reasoning attached, which is the
end state the config's own policy asks for — raising the fixture's floor to 3.12 would trade a real
property of the fixture (it is the lowest-common-denominator consumer, deliberately) for cosmetics.
The upstream one only becomes worth doing if the stub starts needing maintenance; one commit in, it
does not.

Revisit if `invoke-stubs` grows past the two narrowings it ships today, or if invoke releases
anything touching `tasks.py`'s signatures.

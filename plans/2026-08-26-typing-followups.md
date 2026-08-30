---
status: landed
updated: 2026-08-30
---

# Two loose ends from the type-checking rollout

## Migrated to

- `invoke-stubs`' own `plans/2026-08-30-stub-gaps-and-upstream.md`, filed there 2026-08-30 — the
  upstream-pyinvoke question and the `task(klass=..., **kwargs)` overload gap. Both are about that
  distribution, not about this repo; they only lived here because this is where the rollout that
  found them happened.
- Nothing, for the third item — see below. It was already finished.

## What it was

Three items carried over from the now-retired `plans/2026-08-25-type-check-warning-noise.md`, whose
settled content lives in [`../contributing/type-checking.md`](../contributing/type-checking.md). The
title said two; there were three, which is part of why the mixed ownership went unnoticed for four
days.

Two were `invoke-stubs` work and have moved. The third was the `sample-service` fixture's
`reportImplicitOverride`: `typing.override` is 3.12+, the fixture declares
`requires-python =
">=3.11"` and has no dependencies to pull `typing_extensions` from, so the choice
was to raise the fixture's floor or keep a line-level suppression.

**That one was never open.** The plan's own recommendation was to keep the line, and the code
already does exactly that, with the reasoning attached at the site
(`tests/fixtures/sample-service/src/sample_service/__main__.py`):

```python
# No `@override`: `typing.override` is 3.12+, this fixture declares >=3.11 and has no dependencies
# to pull `typing_extensions` from. Suppressed per line so the shared config's
# `failOnWarnings` can stay on.
```

A decision that is implemented, and documented where a reader meets it, is not deferred work. It was
tagged `[DEFERRED:]` because it _could_ be revisited, which is not the same thing — and that is the
tagging mistake worth remembering: the tag marks work still wanted, not options still theoretically
open.

Raising the floor to 3.12 stays the wrong trade for its own reason, also already recorded: the
fixture is deliberately the lowest-common-denominator consumer, and that is a real property to keep
rather than spend on cosmetics.

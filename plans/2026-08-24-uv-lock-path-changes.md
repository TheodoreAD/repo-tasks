---
status: idea
updated: 2026-08-24
---

# `uv lock` cannot re-resolve a workspace member that moved

## Context

Sibling to `plans/2026-08-23-uv-lock-on-version-bump.md`, which covers a different way `uv.lock`
gets into a state a plain `uv lock` will not fix (the version-bump interaction,
[astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643)). Same file, different cause, so
it is tracked separately rather than folded in.

[PITFALL: moving a `[tool.uv.workspace]` member to a new path makes `inv deps.lock` fail outright
rather than re-resolve. `uv.lock` records the member's `source = { editable = "<path>" }`, and uv
reads that stale entry before noticing the manifest changed:

```
error: Failed to generate package metadata for `sample-service==0.1.0 @ editable+examples/sample-service`
  Caused by: Distribution not found at: file:///.../examples/sample-service
```

Confirmed live 2026-08-24 moving the dogfood sample from `examples/sample-service` to
`tests/fixtures/sample-service`. `inv deps.lock --package <member>` (`uv lock --upgrade-package`)
re-resolves it and succeeds; a plain `inv deps.lock` never will, however many times it is run.]

The failure is loud, so nothing ships broken — but the message names a path that no longer exists
and says nothing about the fix, and the obvious next move (run `uv lock` again) does not work.

## Open questions

[NEEDS CLARIFICATION: is this worth any code at all? `deps.lock` could catch the "Distribution not
found at" failure and print the `--package` retry, following `gitflow.py`'s `_next_steps()`
convention of naming the exact command to run next. Against: it is a one-line fix once known, it
only bites when a member moves (rare), and this package's conventions push back on wrapping every
upstream error message. The cheaper answer may be that this plan existing _is_ the fix — a future
session greps `plans/` and finds it.]

[NEEDS CLARIFICATION: does the same trap apply to a member that is _renamed_ rather than moved, or
removed outright? Not tested. If removal also wedges the lock, the guidance is broader than "moving
a member" and belongs in `contributing/` rather than only here.]

[NEEDS CLARIFICATION: does `deps.check` (`uv lock --check`) report this cleanly, or does it fail
with the same confusing message? It is the task most likely to hit the state first in CI, so its
behaviour decides whether this is a developer-only annoyance or a CI one.]

## Recommended direction

Answer the three questions above by measurement before writing any code — particularly the third,
which decides whether this is worth more than a plan file at all. If a fix does land, the
print-the-next-command shape is the one this package already uses for recoverable failures.

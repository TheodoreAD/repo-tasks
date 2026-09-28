---
status: landed
updated: 2026-09-29
source_repo: github.com-personal/invoke-stubs
source_session: b418c54c-c032-4559-9cf3-6370d926625b.jsonl
source_moment: 2026-09-28T19:55:00Z
source_plan:
---

# Lock-pinning consumers tracked main, not tags

## Context

`contributing/consumer-sweep.md` says `power-user-linux-setup` and `invoke-stubs` have no bootstrap
script and "pin through their own lock, so the step is a no-op there and the
`inv deps.lock --package repo-tasks` at the top is their equivalent". It was not an equivalent: both
declared repo-tasks as a bare git URL with no ref, so the re-lock resolves **`main`**, while `stamp`
pins a bootstrap to a **tag**. The two lock-pinning consumers silently kept the pre-2026-09-26
behaviour the pinning decision exists to remove — nothing reports it, since `consumers.diff` checks
a bootstrap pin and these have none.

State as of filing:

- `invoke-stubs`: fixed in `9c5810b`, `repo-tasks @ git+…@v0.6.0` in its dev group.
- `power-user-linux-setup`: filed for that repo as `2026-09-28-pin-repo-tasks-to-a-release-tag.md`,
  absorbed within the minute by a session there, which put `tag = "v0.6.0"` on its
  `[tool.uv.sources]` entry. Check its history for the commit rather than trusting this line.

## Evidence

The `invoke-stubs` v0.6.0 sweep ran `inv deps.lock --package repo-tasks` and got
`Updated repo-tasks v0.5.0 (023363c4) -> v0.6.0 (872dc55d)`; the v0.6.0 tag commit is `a2d9cf5`, and
`872dc55` was four commits past it. The user asked "any reason we are not using the tag?".

## Open questions

[DECISION: **yes, on the declared ref, not the locked commit.** A re-lock moves within the declared
ref, and each consumer's own gate runs `uv lock --check`, so a lock out of step with its declaration
already fails there. Reading the declaration is one TOML parse with no git and no network, the same
shape as the bootstrap check. Landed 2026-09-29 in `d15c761`.]

## Migrated to

- The pitfall and the corrected equivalent of `stamp`: `contributing/consumer-sweep.md`, beside the
  stamp step, plus a one-line comment on the loop's first command.
- The check: `_lock_pin_line` in `src/repo_tasks/consumers.py`, whose docstring carries the
  incident; tests in `tests/unit/test_consumers.py`.
- Not migrated: the per-consumer fix state. Both consumers are pinned to `v0.6.0`, which
  `consumers.diff` now reports on every run.

## Recommended direction

Rewrite the sweep doc's sentence: for a lock-pinning consumer the equivalent of `stamp` is editing
the declared tag **and** re-locking, and a bare re-lock only moves within that tag. Move the
`deps.lock --package repo-tasks` comment at the top of the per-consumer loop to match. Then decide
the open question.

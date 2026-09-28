---
status: idea
updated: 2026-09-28
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

[NEEDS CLARIFICATION: should `consumers.diff` report a lock-pinning consumer whose repo-tasks
declaration has no tag, or whose locked commit is not a tag commit — the same check it already runs
on a bootstrap's pin? That turns this back into something that runs rather than a sentence.]

## Recommended direction

Rewrite the sweep doc's sentence: for a lock-pinning consumer the equivalent of `stamp` is editing
the declared tag **and** re-locking, and a bare re-lock only moves within that tag. Move the
`deps.lock --package repo-tasks` comment at the top of the per-consumer loop to match. Then decide
the open question.

---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/invoke-stubs
source_session: b418c54c-c032-4559-9cf3-6370d926625b.jsonl
source_moment: 2026-09-28T19:40:00Z
source_plan:
---

# consumer-sweep.md still says invoke-stubs has no CI

## Context

`contributing/consumer-sweep.md`, "Still open", last bullet, says `invoke-stubs` has no `.github/`,
so its local gate is the whole of the evidence for a sweep and the security caller cannot be added
until that repo decides whether it wants CI.

That stopped being true before the v0.6.0 sweep. `invoke-stubs` has `.github/workflows/ci.yml`
(`inv quality.check` plus `inv test.integration` on every push and PR) and `security.yml` calling
`security-reusable.yml`, now pinned to `a2d9cf5 # v0.6.0`. `consumers.diff` already reads that
caller — this repo's own v0.6.0 sweep plan cited its pin as `9398008`.

## Evidence

Found during the v0.6.0 sweep of `invoke-stubs`, reading the sweep doc at its "Still open" section:
"`invoke-stubs` has no `.github/`, so its local gate is the whole of the evidence". The same sweep
re-pinned the caller in `invoke-stubs` `cf7cab2`, pushed.

## Recommended direction

Drop the bullet, or rewrite it as the general reading it stands for (whether a consumer has CI at
all) without naming `invoke-stubs`. Check the table above it and the `stamp` paragraph for other
claims about `invoke-stubs` while there — the `stamp` one ("no bootstrap script, pins through its
own lock") still holds.

---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/power-user-linux-setup
source_session: b73129dd-6136-41c3-a026-8e871581bc14.jsonl
source_moment: 2026-09-27T21:05:00Z
source_plan:
---

# check-currency ignores the manifest constraint

## Context

`inv deps.check-currency` (v0.5.0) compares each `repo-tasks-quality` entry's locked version with
the package's **latest release**, not with the latest release the entry's own constraint allows. The
manifest pins `hadolint-py!=2.15.1.2`, and 2.15.1.2 is the only release newer than 2.14.0.1, so the
entry is reported `BEHIND — latest 2.15.1.2` permanently, and the suggested
`inv deps.lock --package hadolint-py` resolves nothing (`Resolved 59 packages`, no change).

A permanent false positive in a currency report is the shape that teaches people to skim it — the
same report that exists because a real lag (`invoke-stubs`, a month) went unread.

## Evidence

Sweeping `power-user-linux-setup` to v0.5.0, 2026-09-28: `check-currency` reported
`hadolint-py 2.14.0.1  BEHIND — latest 2.15.1.2` before and after
`inv deps.lock --package hadolint-py`, whose output was `Resolved 59 packages in 304ms` with no
update. That repo's `pyproject.toml` dev group carries `"hadolint-py!=2.15.1.2"`, matching the
manifest.

## Open questions

[NEEDS CLARIFICATION: compare against the newest release satisfying the consumer's declared
specifier, or the manifest's? They agree today; the consumer's is what the lock actually resolves
against.]

## Recommended direction

Filter the release list through the entry's `SpecifierSet` (`packaging`) before taking the max, and
when the newest release is excluded, say so on the line
(`current — 2.15.1.2 excluded by
!=2.15.1.2`) rather than hiding it, so the exclusion stays visible
without reading as a lag.

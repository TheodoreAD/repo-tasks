---
status: landed
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

~~[NEEDS CLARIFICATION:~~ compare against the newest release satisfying the consumer's declared
specifier, or the manifest's? They agree today; the consumer's is what the lock actually resolves
against.]

[DECISION: **neither specifier: ask the resolver.** Chosen by the user 2026-09-28. Each entry
`uv tree --outdated` flags is confirmed with `uv lock --dry-run --upgrade-package <name>`, which
resolves under the consumer's own constraints and index configuration. It answers the report's real
question, whether the suggested `deps.lock --package` would move anything. The recommended direction
below, filtering a release list through a `SpecifierSet`, was set aside for two reasons. `uv tree`
gives no release list, so it would need a second index client, and that client would ignore the
consumer's index settings, which `uv tree` was chosen to honour. The cost is one resolve per flagged
entry, measured at 0.3 to 1.1s. The exclusion stays visible, as the direction asked, but as
`current — latest X is excluded by this project's constraints` rather than naming the specifier,
which the resolver does not report.]

Landed in `08f17fe`, three new unit tests failing against the previous code. On this repo's own
lock, `hadolint-py 2.14.0.1  current — latest 2.15.1.2 is excluded by this project's constraints`,
where it used to say BEHIND.

## Migrated to

- `src/repo_tasks/deps.py`, `_registry_verdict`'s docstring and `check_currency`'s: the failure, the
  mechanism, and why it answers the right question.
- `tests/unit/test_deps.py`: the excluded, allowed-below-excluded and failed-dry-run cases.

Deliberately not migrated: the evidence from the power-user-linux-setup sweep. The same false
positive reproduces on this repo's own lock, and the docstring cites that.

## Recommended direction

Filter the release list through the entry's `SpecifierSet` (`packaging`) before taking the max, and
when the newest release is excluded, say so on the line
(`current — 2.15.1.2 excluded by
!=2.15.1.2`) rather than hiding it, so the exclusion stays visible
without reading as a lag.

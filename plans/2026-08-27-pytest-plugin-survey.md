---
status: idea
updated: 2026-09-05
---

# Which pytest plugins should the family standardise on?

## Context

`repo-tasks-quality` ships three pytest plugins — `pytest-cov`, `pytest-socket` and, since
2026-08-30, `pytest-timeout`. The first two arrived one concern at a time from the quality-gate
coverage sweep, never from a survey; the user asked for one 2026-08-27: "we should also look for
other very common pytest plugins to include ... I forgot to do this."

**The survey ran 2026-08-30 and its results are no longer here.** Migrated 2026-09-05 to
[`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Pytest plugins: what ships, what
is recommended, what was rejected": the inertness criterion and how it was measured, the pty
pitfall, the concern sweep, the one adoption, the nine named recommendations and the thirteen
recorded rejections, and the measurement that the socket guard does not interfere with the
HTTP-mocking candidates. Its conclusion was narrow — the family was missing exactly one plugin — and
the recommend/reject tables are the more valuable half, since "why not `pytest-sugar`" is what stops
this being surveyed a third time.

What stays here is what is still open, and one measurement caveat.

## Open questions

[NEEDS CLARIFICATION: whether a non-inert plugin can be adopted _with_ its behaviour disabled by the
shipped `pytest.ini` — `pytest-randomly` has `-p no:randomly`, for instance. That would make the
inert-by-default rule a property of the config rather than of the plugin, which is a weaker but
possibly acceptable bar. It also puts more behaviour in a file every consumer inherits, which is the
coupling `test-tiers.md` already flags. Moot unless someone wants `pytest-randomly` specifically —
it is the only rejection this would reopen, since `pytest-sugar` has no equivalent switch worth
shipping.]

[NEEDS CLARIFICATION: whether this survey should cover the _generated_ repo's plugins separately.
`scaffoldapy` picks dependencies per interface, so an async plugin for `web_service`/`mcp_server`
may belong in the template rather than in the shared manifest — the same split that repo is working
out for the test tree itself, in its own `plans/2026-08-30-generated-test-layout.md` (filed there
from here on 2026-08-30). `syrupy` is the concrete case: it is recommended rather than shipped
precisely because that repo, not this one, has the snapshot concern.]

[UNVERIFIED: the inertness runs used `uv run --with`, which resolved CPython 3.14.5, while the
repo's own gate runs the pinned 3.11.15. Every candidate passed on both, so nothing migrated rests
on the difference, but an adoption decision that turns on version-specific behaviour should be
re-measured on the floor.]

[DEFERRED: this plan proposes no change to the two originally shipped. `pytest-cov` and
`pytest-socket` were decided separately and on their own merits; nothing here revisits them.]

## Recommended direction

Nothing further until one of the two questions is asked for its own reasons. The second is really
`scaffoldapy`'s to answer. When both are settled, retire: the migration is done, and this file
carries nothing else.

---
status: idea
updated: 2026-08-24
---

## Context

Split out of `plans/2026-08-23-test-tiers-and-dependency-groups.md`, which folds every dependency
group into `dev`. That decision is right and lands independently; this plan is only about the one
uncomfortable consequence, deliberately deferred.

`devpi-server` and `devpi-client` exist solely to give `tests/integration/test_dist_integration.py`
a real PEP 691/503 package index to run `dist.py`'s `versions`/`publish` against. Measured
2026-08-24:

| dependency       | packages resolved standalone |
| ---------------- | ---------------------------- |
| `devpi-server`   | 43                           |
| `devpi-client`   | 18                           |
| `testcontainers` | 10                           |

Folding them into `dev` takes a plain `uv sync` from 39 packages to roughly 82 — most of it devpi's
pyramid/zope stack, for two tests.

**Explicitly not urgent.** It works today, disk is not a constraint, and `uv` is fast enough that
the install cost is not felt. This is filed because it is untidy, not because it hurts.

## Open questions

[NEEDS CLARIFICATION: can a stub HTTP server replace devpi outright? What the two tests actually
need is an endpoint serving PEP 691 JSON on the right `Accept` header and PEP 503 HTML otherwise —
`http.server` in a thread can do both, with no dependency at all.
[`contributing/test-tiers.md`](../contributing/test-tiers.md) records devpi being chosen over
`pypiserver` specifically because `pypiserver` serves only the HTML index, leaving `dist.py`'s JSON
branch untested — that argument is about `pypiserver`, not about stubs, and a stub controls both
branches directly.]

[NEEDS CLARIFICATION: what would be lost? devpi is a real implementation, and the tier's stated
value is catching what mocked fixtures cannot — it found two genuine `dist.py` bugs on first run (a
missing PEP 691 `version` key, and `#sha256=` fragments in HTML hrefs), both now pinned by unit
regressions. A stub written today would encode what we already know and would not have found those.
The honest question is whether that discovery value recurs, or whether it was a one-time payoff
already banked.]

[NEEDS CLARIFICATION: is `uv publish` exercisable against a stub at all? `dist.publish` is half of
what this tier covers, and a stub would need to accept a real upload. That may be the piece that
keeps a real server necessary even if `versions` moves to a stub — in which case the split is
per-test, not per-tier.]

## Recommended direction

Leave it alone until one of two things changes: the install weight starts being felt, or the
integration tier stops earning its keep. Revisit then with the questions above answered by
measurement rather than argument — particularly the third, which likely decides the whole thing.

If it is revisited and a stub wins, the replacement belongs next to the tests it serves, not as a
fixture in `conftest.py` shared with unrelated modules.

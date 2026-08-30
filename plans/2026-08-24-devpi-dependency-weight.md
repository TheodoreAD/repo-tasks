---
status: landed
updated: 2026-08-30
---

# devpi's weight in the dev group

## Migrated to

- [`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Package index: a real server
  for the HTML branch, a stub for the JSON one" — the reversal and its numbers, the 409-on-re-upload
  pitfall, and the decision that a stub covers more of `_json_versions` than any real index does.
  The "What this tier caught" section now says which server found the two original bugs, and the
  closing lesson gained the half this plan supplied: re-ask a tool choice when its _cost_ changes,
  not only when the candidates do.
- [`../contributing/quality-gate.md`](../contributing/quality-gate.md) — the no-suppression decision
  gained the worked example it lacked: an advisory really did block work, the rule held, and the fix
  was removing the dependency rather than suppressing its finding.
- [`2026-08-30-deps-audit-in-ci.md`](2026-08-30-deps-audit-in-ci.md) — the `[DEFERRED:]` CI audit
  step, which this plan blocked and which is now unblocked. Filed as its own plan rather than left
  as a sentence in `quality-gate.md`.

**Not migrated:** the original per-package resolution table (43 + 18 + 10). It measured a dependency
set that no longer exists; the numbers that matter now (98 → 63 packages, 61 → 4 for the index) are
in `test-tiers.md`.

## What it was

`devpi-server` and `devpi-client` existed solely to give
`tests/integration/test_dist_integration.py` a real PEP 691/503 package index to run `dist.py`'s
`versions`/`publish` against. Filed 2026-08-24 because that was untidy — 61 resolved packages of
pyramid/zope stack for two tests — and explicitly _not_ urgent: it worked, disk was not a
constraint, and `uv` made the install cost unnoticeable.

It stopped being about tidiness on 2026-08-26, when `inv deps.audit` reported two advisories against
`setuptools` 81.0.0 that the lock could not move away from: `devpi-server` requires `setuptools<=81`
and its `pyramid` dependency `<82`. That blocked a decision already taken — the push-triggered
`deps.audit` CI step — because it would have been red from its first run.

## How it was settled

Measured 2026-08-30 rather than argued, which reversed the plan's own expectations twice.

The plan's third question — whether `uv publish` could work against a stub at all — guessed that the
upload might be what kept a real server necessary. Measured, the upload is the easy half:
`uv publish` uploads to pypiserver without complaint. What nothing lightweight does is the **JSON**
half. pypiserver still serves no PEP 691 at all (it answers `text/html` whatever the `Accept` header
says), and `simple-repository-server`, which does implement PEP 691, pulls `fastapi` +
`uvicorn[standard]` + `httpx` and accepts no uploads. So the split is per-test as the plan
suspected, but on the opposite axis.

The plan's second question — what a stub would lose — turned out to have a better answer than
"something". `_json_versions` has three sub-paths, and no real index emits all three: PyPI takes the
top-level `versions` key and omits the per-file `version` key entirely, devpi took the
filename-derivation path, and **nothing produces the middle one**, which was therefore mock-only for
as long as devpi was the fixture. A stub serves all three, over a real socket, and can assert the
JSON media type actually reached the wire — which a mocked `_get` cannot show and a real server
cannot be made to report. Coverage went up, not down: 2 tests became 5.

Outcome: 98 packages to 63, `setuptools` gone from the lock entirely, `inv deps.audit` at zero
vulnerabilities, and the integration tier still doing a real build → real `uv publish` → real HTML
parse round trip against a real index.

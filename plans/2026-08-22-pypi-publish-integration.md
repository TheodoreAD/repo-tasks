---
status: planned
updated: 2026-08-23
---

## Context

`dist.py` (`build`/`publish`/`versions`) landed in `plans/2026-08-19-python-package-tasks.md` and
has already been hand-exercised against the real public index in a prior session: `versions()`
correctly parsed all 420 real releases of `ruff` from `pypi.org` via the PEP 691 JSON path, and
`publish --dry-run` reached the real `https://upload.pypi.org/legacy/` endpoint (failing only on
missing credentials, as expected — no accidental upload). That plan's Design §4 ("Dogfood publish
plan") already sketches the eventual goal in one loose paragraph; this plan is the concrete
follow-through on it.

Depends on `plans/2026-08-22-local-index-and-registry-testing.md` for the routine, every-commit-
safe testing tier (a local `devpi-server`) — that plan is what gets exercised on every
`inv quality.test`. This plan covers the real, external `test.pypi.org`/`pypi.org` instead:
deliberate, occasional, manual/CI-triggered, never run automatically on a schedule or on every
commit — rate limits, real long-lived-if-mismanaged credentials, and genuinely irreversible side
effects.

[PITFALL: a version number once uploaded to real PyPI can never be re-uploaded or reused, even after
deleting the release. There is no undo and no second attempt at the same version — which is why §1
below makes TestPyPI unconditionally first, and why `--dry-run` is a local iteration tool rather
than the safety gate.]

## Design

### 1. TestPyPI first, always

Prove the entire pipeline — name registration, upload, version query, a real `uv add` install from
it — against `test.pypi.org` before ever touching the real index. TestPyPI exists specifically for
this; there's no reason to risk the real index's one-shot irreversibility for first-run debugging.

### 2. Named index config (`pyproject.toml`)

Confirmed via `uv`'s own docs: `[[tool.uv.index]]` supports `name`, `url`, `publish-url`,
`explicit`, `default`, `authenticate`, and a few more specialized keys. Add one entry for
`testpypi`:

```toml
[[tool.uv.index]]
name = "testpypi"
url = "https://test.pypi.org/simple/"
publish-url = "https://test.pypi.org/legacy/"
explicit = true
```

`explicit = true` keeps this index out of ordinary dependency resolution entirely — it's only ever
consulted when a command names it directly (`inv dist.publish --index testpypi`,
`inv dist.versions --index testpypi`, or a scratch project's own
`uv add --index testpypi repo-tasks` for verification). Real PyPI needs no named entry at all — it's
`uv`'s own implicit default index already, so bare `inv dist.publish`/`inv dist.versions` (no
`--index`) already targets it correctly, exactly as landed.

### 3. Auth: Trusted Publishing (OIDC) primary, API token as the manual/local fallback

Trusted Publishing is PyPI's own current recommended default — no long-lived secret stored anywhere
to leak or rotate. `uv publish` already supports it natively (confirmed via `uv publish --help`):
`--trusted-publishing {automatic,always,never}`, where `automatic` detects a supported CI OIDC
environment (GitHub Actions) and exchanges its short-lived ID token for a short-lived PyPI upload
token itself.

Setup is a one-time manual step on both `test.pypi.org` and `pypi.org`'s web UI — create a "pending
publisher" tied to `TheodoreAD/repo-tasks`, a specific workflow filename, and (optionally) a named
GitHub Environment. This can't be automated from `inv`/CI; it's tracked here as an explicit
checklist item, done once, by a human, before the first CI-driven publish.

API-token auth (`--token`/`UV_PUBLISH_TOKEN`) stays documented as the fallback for a human
publishing manually from their own machine outside CI (e.g. an early manual TestPyPI push before CI
exists yet) — the token lives in the human's own secret manager, never committed to this repo.

### 4. CI workflow (new — this repo has no GitHub Actions workflows at all yet)

`.github/workflows/publish.yml`, triggered on a `vX.Y.Z` tag push (matches `version.py`'s existing
tag scheme from `plans/2026-08-19-release-management.md`), with `permissions: id-token: write`
(required for OIDC trusted publishing). Steps: `inv dist.publish --index testpypi` first
(unconditional), then `inv dist.publish` against real PyPI gated behind a GitHub Environment
protection rule requiring manual approval — _that_ protection rule is the actual safety gate
ensuring a human confirms before the irreversible real-PyPI step, not `--dry-run` (which stays a
local-iteration tool, not a CI gate).

### 5. Rollout order

1. Reserve/confirm the name on TestPyPI, publish `0.1.0` there for real, confirm
   `inv dist.versions --index testpypi` sees it and a scratch project's
   `uv add --dev --index testpypi repo-tasks` actually installs it.
2. Confirm the name is still unclaimed on real PyPI. Note: `inv dist.versions` reporting "no
   releases found" today only means nothing's been _uploaded_ under that name yet — it doesn't prove
   the name itself isn't already reserved by someone else. Real confirmation only happens at the
   first upload attempt.
3. Wire the CI workflow + environment protection rule.
4. First real-PyPI publish is a deliberate, human-approved action — never something an agent runs
   proactively, matching this repo's own "irreversible external action" posture.

## Files touched

- `pyproject.toml` — `[[tool.uv.index]]` `testpypi` entry.
- `.github/workflows/publish.yml` (new).
- `README.md` — document the eventual `uv add repo-tasks` PyPI install path as an alternative to the
  git-dependency one, once real.
- `plans/2026-08-19-python-package-tasks.md` — Design §4 gets a one-line cross-reference to this
  plan instead of carrying the loose paragraph as the only record.

## Verification

- `inv dist.publish --index testpypi --dry-run` locally against the real endpoint — already done in
  a prior session, confirms command construction is correct. [UNVERIFIED: none of §5's rollout has
  actually been done — no TestPyPI publish, no trusted-publisher setup on either index, no CI
  workflow, and the name's availability on real PyPI is still unconfirmed (`dist.versions` reporting
  "no releases" proves only that nothing was uploaded under that name, not that it is unclaimed).
  Each of these is a manual, human-supervised, one-time step — never automated, and never triggered
  by an agent without explicit confirmation immediately beforehand, given the irreversibility
  above.]

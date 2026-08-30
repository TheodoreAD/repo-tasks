---
status: blocked on the one-time manual trusted-publisher setup on TestPyPI and PyPI, which only a human can do
updated: 2026-08-30
---

## Context

`dist.py` (`build`/`publish`/`versions`) has landed, and has already been hand-exercised against the
real public index in a prior session: `versions()` correctly parsed all 420 real releases of `ruff`
from `pypi.org` via the PEP 691 JSON path, and `publish --dry-run` reached the real
`https://upload.pypi.org/legacy/` endpoint (failing only on missing credentials, as expected — no
accidental upload). The now-retired `plans/2026-08-19-python-package-tasks.md` sketched this as a
"dogfood publish plan" in one loose paragraph; this plan is the concrete follow-through on it.

Depends on the routine, every-commit-safe testing tier — a local `devpi-server`, per
[`contributing/test-tiers.md`](../contributing/test-tiers.md) — which is what gets exercised on
every `inv test.unit`. This plan covers the real, external `test.pypi.org`/`pypi.org` instead:
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
`inv dist.list-versions --index testpypi`, or a scratch project's own
`uv add --index testpypi repo-tasks` for verification). Real PyPI needs no named entry at all — it's
`uv`'s own implicit default index already, so bare `inv dist.publish`/`inv dist.list-versions` (no
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

API-token auth stays the fallback for a human publishing manually from their own machine outside CI
(e.g. an early manual TestPyPI push before CI exists yet) — the token lives in the human's own
secret manager, never committed to this repo.

**What that secret manager is, settled 2026-08-30:** the OS secret store, per the household rule
that anything needing a password goes through each tool's own native integration. `uv` has one, and
it is the "call the `keyring` CLI" shape the rule asks for rather than a library dependency — `uv`
supports keyring in **subprocess mode only**. Confirmed against `uv 0.11.19`'s own
`uv publish --help`: `--keyring-provider <disabled|subprocess>`, also settable as
`keyring-provider = "subprocess"` in `uv.toml`/`[tool.uv]` or `UV_KEYRING_PROVIDER`.

The human stores the token once, against the publish URL as the service and the literal `__token__`
as the username, and `uv publish --keyring-provider=subprocess --username=__token__` reads it back.
Nothing here ever handles the token.

[PITFALL: two traps, and either one makes this look configured while doing nothing. **`uv` consults
keyring only when the index URL carries a username** — for PyPI that username is the literal
`__token__`, and without it the lookup silently never happens. And `--keyring-provider=subprocess`
combined with `--token` fails outright with "a value is required for '--token <TOKEN>' but none was
supplied": [astral-sh/uv#9227](https://github.com/astral-sh/uv/issues/9227), open since 2024 and
labelled documentation rather than fixed. `--username=__token__` **instead of** `--token` is the
working invocation, not an addition to it.]

The machine-side half of this — the `uv.toml` key, and the human-facing instruction for what to
store where — is filed for `power-user-linux-setup` as
`2026-08-30-os-secret-store-for-registries-and-pypi.md`, since a task cannot configure the machine
it runs on.

### 4. CI workflow

`.github/workflows/publish.yml` (landed 2026-08-24, alongside the existing `ci.yml` and the docker
workflows), triggered on a `vX.Y.Z` tag push (matches `version.py`'s existing tag scheme, per
[`contributing/versioning.md`](../contributing/versioning.md)) or by hand, with
`permissions: id-token: write` (required for OIDC trusted publishing). Two jobs:
`inv dist.publish --index testpypi` first (unconditional), then `inv dist.publish` against real PyPI
in the `pypi` GitHub Environment, whose required-reviewer protection rule is the actual safety gate
ensuring a human confirms before the irreversible real-PyPI step — not `--dry-run` (which stays a
local-iteration tool, not a CI gate). The workflow cannot succeed until §5's manual steps are done:
neither index has a pending publisher registered, and the `pypi` environment does not exist yet.

### 5. Rollout order

1. Reserve/confirm the name on TestPyPI, publish `0.1.0` there for real, confirm
   `inv dist.list-versions --index testpypi` sees it and a scratch project's
   `uv add --dev --index testpypi repo-tasks` actually installs it.
2. Confirm the name is still unclaimed on real PyPI. Note: `inv dist.list-versions` reporting "no
   releases found" today only means nothing's been _uploaded_ under that name yet — it doesn't prove
   the name itself isn't already reserved by someone else. Real confirmation only happens at the
   first upload attempt.
3. Wire the CI workflow + environment protection rule.
4. First real-PyPI publish is a deliberate, human-approved action — never something an agent runs
   proactively, matching this repo's own "irreversible external action" posture.

## Files touched

- (Done) `pyproject.toml` — `[[tool.uv.index]]` `testpypi` entry; `uv lock --check` unaffected.
- (Done) `.github/workflows/publish.yml`, inert until the manual setup in §5 — see §4.
- `README.md` — document the eventual `uv add repo-tasks` PyPI install path as an alternative to the
  git-dependency one, once real.
- (Done) the loose "dogfood publish plan" paragraph that used to be the only record of this lived in
  `plans/2026-08-19-python-package-tasks.md`, now retired — this plan is that record.

## Verification

- `inv dist.publish --index testpypi --dry-run` locally against the real endpoint — already done in
  a prior session, confirms command construction is correct. [UNVERIFIED: none of §5's rollout has
  actually been done — no TestPyPI publish, no trusted-publisher setup on either index, no CI
  workflow, and the name's availability on real PyPI is still unconfirmed (`dist.list-versions`
  reporting "no releases" proves only that nothing was uploaded under that name, not that it is
  unclaimed). Each of these is a manual, human-supervised, one-time step — never automated, and
  never triggered by an agent without explicit confirmation immediately beforehand, given the
  irreversibility above.]
- [UNVERIFIED: `publish.yml`'s rc gating (a `vX.Y.ZrcN` tag runs the TestPyPI job and skips the
  `pypi` job via `!contains(github.ref_name, 'rc')`) — landed 2026-08-25 from the now-retired
  `plans/2026-08-25-prerelease-versions.md`, checked by actionlint only. The first
  `inv gitflow.release-candidate` push after this rollout is the real test; confirm the `pypi` job
  shows as skipped, not failed, in that run.]

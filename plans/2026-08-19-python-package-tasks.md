---
status: landed
updated: 2026-08-22
---

## Context

Goal includes building and pushing python packages reproducibly via `inv`. Unlike the docker/helm
plans, this one has an immediate real exerciser: `repo-tasks` itself is a python package (hatchling
backend, `src/repo_tasks`, already built implicitly whenever a consumer does
`uv add --dev git+https://github.com/TheodoreAD/repo-tasks`). Depends on
`plans/2026-08-19-monorepo-workspace-foundation.md` for multi-project iteration later, and on
`plans/2026-08-19-release-management.md` as the sole writer of each project's version.

**2026-08-20 update:** folded into a three-module split alongside
`plans/2026-08-20-venv-deps-tasks.md` (`venv.py` for venv lifecycle, `deps.py` for lock-file
operations). This plan's module is renamed from the original `python_pkg.py` to **`dist.py`** to
match that split, and gains `clean`/`versions` tasks (Design §1 below) — the sibling plan covers
venv/deps only, not repeated here.

Decision from review: include `publish(c)`, not just `build(c)`. `repo-tasks` will itself eventually
be published to PyPI as a deliberate dogfood of the `publish` task — proving it against a real
index, not just a private/test one — while the git-dependency install path documented in README.md
stays the primary, supported route. PyPI becomes an _additional_ channel, not a replacement.

## Design

### 1. `src/repo_tasks/dist.py` (renamed from this plan's original `python_pkg.py`)

- `clean(c)` — remove the built `dist/` directory. Exact `docs.clean` pattern (`shutil.rmtree` if
  present, else a "nothing to clean" no-op message) — same shape, different directory.
- `build(c, project=None, sdist=False)` — `pre=[clean]`, matching `docs.build`'s own `pre=[clean]`
  shape, so a stale wheel from a previous version can never survive into a fresh build. Defaults to
  `uv build --wheel` (confirmed via `uv build --help`) — the request asked for "build distribution
  as wheel" specifically; `sdist=True` drops `--wheel` and runs plain `uv build` for the sdist+wheel
  pair PyPI conventionally expects. No twine/setuptools dependency; `uv build` covers both natively.
- `publish(c, project=None, index=None, dry_run=False)` — `pre=[build]` (which itself implies
  `clean`), so publish always ships a just-built, correct `dist/` rather than whatever happened to
  be sitting there — strengthens the "never mutate/ship stale state" posture the sibling
  `plans/2026-08-20-venv-deps-tasks.md` establishes for `venv`/`deps`, applied here to build
  freshness rather than lock freshness. Runs `uv publish` (`--index <index>` when given, else uv's
  own default-index/config resolution) with `--dry-run` passed through for safe testing against a
  real index without actually uploading (confirmed flag via `uv publish --help`).
- `versions(c, project=None, index=None)` — "get published versions/list" from the request. `uv`
  itself has no subcommand for this (checked `uv --help` and `uv pip --help` — no
  list-remote-versions command exists), so this hand-rolls a query against the standardized index
  protocol instead of screen-scraping error text: PEP 691 JSON Simple API
  (`Accept: application/vnd.pypi.simple.v1+json`) via stdlib `urllib.request` against
  `<index>/<project-name>/` (default index: PyPI's `https://pypi.org/simple/`), falling back to
  parsing the PEP 503 HTML file listing if the server doesn't serve the JSON media type — works
  unmodified against PyPI, TestPyPI, or any private PEP 503/691-compliant index. No new dependency:
  stdlib only. Project name resolved via `projects.discover_python_projects(c)` rather than
  hardcoded, matching this package's existing "never hardcode the repo root" convention.

### 2. Not part of the quality composite

Deliberately _not_ folded into `fix`/`check`/`precommit` — building/publishing a package is a
release-time action, not an every-commit action, matching how `fix`/`check` already stay distinct
from anything install- or publish-adjacent. `publish` in particular is never invoked from any
automated composite given its irreversible, external-facing nature — always a deliberate, standalone
`inv dist.publish`.

### 3. Version is read-only here

`dist.py` never writes a version itself — it only reads whatever `version.py`
(`release-management.md`) already wrote to the project's `pyproject.toml`. Single writer for that
field avoids two task modules racing to touch the same value.

### 4. Dogfood publish plan

Once `repo-tasks`'s task-module surface is stable enough to commit to a public API, publish it to
PyPI as `repo-tasks` (name availability to be checked at that time) using this very `publish` task,
authenticated via a PyPI API token or trusted-publisher OIDC config set up in CI at that point —
that setup is a one-time account/CI-secret step tracked separately when it's actually attempted, not
part of this plan's file changes. See `plans/2026-08-22-pypi-publish-integration.md` for the
concrete follow-through on this paragraph (TestPyPI-first rollout, trusted-publishing setup, CI
workflow).

### 5. Monorepo phase

Phase 1 (this repo, single implicit project): `build(c)`/`publish(c)`/`versions(c)` run bare
`uv
build`/`uv publish`/index query against the repo root, no `--project` flag needed. Phase 2:
iterate `projects.py`'s discovered members, or scope to one via `uv build --package <name>` /
`--project=<name>`.

### 6. No interaction with venv/CI-editable mode

`dist.py` never touches `.venv` or installs anything editable — `uv build` always produces a real,
non-editable sdist/wheel regardless of how the _dev_ environment happens to be installed, so the
sibling `plans/2026-08-20-venv-deps-tasks.md`'s `--no-editable`/CI-mode design has nothing to plug
into here; the two modules are orthogonal by construction.

## Files touched

- `src/repo_tasks/dist.py` (new)
- `src/repo_tasks/__init__.py` — nest the new `dist` collection into `ns` alongside the existing
  ones (no consumer-side `tasks.py` change needed, per the existing `ns` design)
- (Later, at actual dogfood-publish time, tracked separately) CI secret/trusted-publisher config for
  a real PyPI upload

## Verification

- Unit tests mocking `c.run` for `clean`/`build`/`publish` command construction, and mocking
  `urllib.request` for `versions`' JSON/HTML parsing (both the PEP 691 success path and the PEP 503
  HTML fallback).
- `inv dist.build` exercised locally against this repo, confirming `uv build --wheel`'s `dist/`
  output and that a stale prior wheel doesn't survive the `clean` pre-task.
- `inv dist.versions` exercised against a real, already-published PyPI package (e.g. `ruff` or
  `invoke`) to confirm parsing against the real index, and against this repo's own not-yet-published
  name to confirm a graceful "no releases found" (404) result before ever attempting a real publish.
- `publish` only ever run deliberately by a human against a real index when the dogfood step is
  actually undertaken — never exercised automatically in CI/tests before then. `--dry-run` is safe
  to exercise earlier, against a real index, without an actual upload.

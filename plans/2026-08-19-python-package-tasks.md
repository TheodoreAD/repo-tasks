---
status: planned
updated: 2026-08-19
---

## Context

Goal includes building and pushing python packages reproducibly via `inv`. Unlike the docker/helm
plans, this one has an immediate real exerciser: `repo-tasks` itself is a python package (hatchling
backend, `src/repo_tasks`, already built implicitly whenever a consumer does
`uv add --dev git+https://github.com/TheodoreAD/repo-tasks`). Depends on
`plans/2026-08-19-monorepo-workspace-foundation.md` for multi-project iteration later, and on
`plans/2026-08-19-release-management.md` as the sole writer of each project's version.

Decision from review: include `publish(c)`, not just `build(c)`. `repo-tasks` will itself eventually
be published to PyPI as a deliberate dogfood of the `publish` task — proving it against a real index,
not just a private/test one — while the git-dependency install path documented in README.md stays
the primary, supported route. PyPI becomes an _additional_ channel, not a replacement.

## Design

### 1. `src/repo_tasks/python_pkg.py`

- `build(c, project=None)` — `uv build` (sdist + wheel into `dist/`). No twine/setuptools
  dependency; `uv build` already covers this natively.
- `publish(c, project=None, index=None)` — `uv publish` (or `uv publish --publish-url <index>` for a
  private index). Defaults to PyPI when `index` is omitted.

### 2. Not part of the quality composite

Deliberately _not_ folded into `fix`/`check`/`precommit` — building/publishing a package is a
release-time action, not an every-commit action, matching how `fix`/`check` already stay distinct
from anything install- or publish-adjacent. `publish` in particular is never invoked from any
automated composite given its irreversible, external-facing nature — always a deliberate, standalone
`inv python-pkg.publish`.

### 3. Version is read-only here

`python_pkg.py` never writes a version itself — it only reads whatever `version.py`
(`release-management.md`) already wrote to the project's `pyproject.toml`. Single writer for that
field avoids two task modules racing to touch the same value.

### 4. Dogfood publish plan

Once `repo-tasks`'s task-module surface is stable enough to commit to a public API, publish it to
PyPI as `repo-tasks` (name availability to be checked at that time) using this very `publish` task,
authenticated via a PyPI API token or trusted-publisher OIDC config set up in CI at that point —
that setup is a one-time account/CI-secret step tracked separately when it's actually attempted, not
part of this plan's file changes.

### 5. Monorepo phase

Phase 1 (this repo, single implicit project): `build(c)`/`publish(c)` run bare `uv build`/`uv
publish` against the repo root, no `--project` flag needed. Phase 2: iterate `projects.py`'s
discovered members, or scope to one via `uv build --package <name>` / `--project=<name>`.

## Files touched

- `src/repo_tasks/python_pkg.py` (new)
- `tasks.py` — wire the new `python_pkg` collection alongside `quality`
- (Later, at actual dogfood-publish time, tracked separately) CI secret/trusted-publisher config for
  a real PyPI upload

## Verification

- Unit tests mocking `c.run` for `build`/`publish` command construction.
- `inv python-pkg.build` exercised locally against this repo, confirming `uv build`'s `dist/` output.
- `publish` only ever run deliberately by a human against a real index when the dogfood step is
  actually undertaken — never exercised automatically in CI/tests before then.

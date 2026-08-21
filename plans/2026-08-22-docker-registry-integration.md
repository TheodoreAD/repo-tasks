---
status: planned
updated: 2026-08-22
---

## Context

`docker.py` (`build`/`push`/`release`) landed in `plans/2026-08-19-docker-image-tasks.md` but has
never been exercised against a real registry — only unit-tested with mocked `c.run`, and this repo
has no Dockerfile of its own yet (`plans/2026-08-19-dogfood-sample-service.md` is still `idea`
status). Depends on that sibling plan for an actual image to push for real; until it lands, this
plan's auth/CI wiring can still be written and even smoke-tested with a throwaway scratch image,
but full end-to-end dogfooding waits on it.

Depends on `plans/2026-08-22-local-index-and-registry-testing.md` for the routine, every-commit-
safe registry testing tier (`registry:3` via `testcontainers`) — that plan covers what gets
exercised on every `inv quality.test`. This plan covers the real, external GHCR instead: deliberate,
occasional, manual/CI-triggered, not run automatically.

## Design

### 1. Registry choice: GHCR, not Docker Hub

GHCR (`ghcr.io`) is clearly easier for a GitHub-hosted repo: CI auth is just the already-issued
`GITHUB_TOKEN` (`permissions: packages: write` on the workflow) — no separate account, no PAT to
create/rotate/store as a repo secret. Docker Hub would need its own account plus an access token
managed entirely outside GitHub's existing trust boundary, for no offsetting benefit here.
`repo-tasks.toml`'s own sample `[[docker]]` config
(`plans/2026-08-19-monorepo-workspace-foundation.md` Design §2) already uses a `ghcr.io/...` image
name, so this is also just confirming the design's existing default rather than introducing a new
decision. GHCR packages default to the same visibility as their owning repo (private stays
private) but can be flipped public per-package via GitHub's UI later if wider distribution is ever
wanted — a one-time manual step, not something `inv`/CI configures.

### 2. `docker.py` itself needs zero changes

Image name/registry/Dockerfile/path already come entirely from
`projects.discover_docker_images(c)` (landed) — either an explicit `repo-tasks.toml` `[[docker]]`
entry or the zero-config root-`Dockerfile` default. This plan is purely about the auth/CI/account
wiring around whatever entry eventually exists, e.g.
`image = "ghcr.io/TheodoreAD/sample-service"` once `dogfood-sample-service.md` lands — not a
`docker.py` design change.

### 3. CI auth: `docker/login-action`, zero new secrets

The standard, documented GHCR-from-GitHub-Actions pattern:

```yaml
- uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

`docker.py`'s own Design §4 (landed, deferred) auth-retry-on-401 logic stays irrelevant for this CI
path specifically — `GITHUB_TOKEN` doesn't expire mid-job, and `docker/login-action` runs once up
front. That retry logic remains meaningful only for a human's local/interactive session hitting a
stale credential, not CI.

### 4. Local/manual auth

`docker login ghcr.io -u <github-username>` with a GitHub Personal Access Token scoped to
`write:packages` (classic PAT — GHCR's fine-grained-PAT support should be re-checked at
implementation time, since GitHub has been expanding fine-grained scopes over time) — a one-time
manual step for a human publishing from their own machine, never stored in this repo.

### 5. CI workflow

`.github/workflows/docker-release.yml` (new — or merged into
`plans/2026-08-22-pypi-publish-integration.md`'s `publish.yml` as a second job, whichever reads
more coherently once both are actually being written), triggered on the same `vX.Y.Z` tag push as
the PyPI publish workflow, running `inv docker.release` — but this has nothing to build until
`dogfood-sample-service.md` lands a real Dockerfile. The auth/login step itself is harmless to
merge early with no image to push yet (just inert); the actual `docker.release` step is explicitly
blocked on that sibling plan.

### 6. Verification order

1. Auth-only smoke test, doable _now_, independent of `dogfood-sample-service.md`: confirm
   `docker/login-action` + `GITHUB_TOKEN` actually authenticates against `ghcr.io` from a throwaway
   workflow run, pushing a trivial scratch image (e.g. re-tagging `hello-world` and pushing it to
   this repo's own GHCR namespace) to prove the wiring alone, before any real Dockerfile exists.
2. Once `dogfood-sample-service.md` lands, real `inv docker.release` exercised end-to-end in CI.
3. Confirm the pushed package appears under the GitHub org/user's Packages tab with the expected
   name and visibility.

## Files touched

- `.github/workflows/docker-release.yml` (new, or a job added to `publish.yml`).
- `repo-tasks.toml` — the real `[[docker]]` entry, added once `dogfood-sample-service.md`'s
  Dockerfile exists (not this plan's own file change).
- `plans/2026-08-19-docker-image-tasks.md` — cross-reference addition pointing at this plan for the
  real-registry piece its own Design deliberately deferred.
- `plans/2026-08-19-dogfood-sample-service.md` — cross-reference addition noting this plan is what
  eventually pushes its image for real, once it lands.

## Verification

- Auth-only smoke test (login + push a throwaway scratch image) — confirmable now, independent of
  `dogfood-sample-service.md`.
- Full `docker.release` round trip against GHCR — blocked on that sibling plan landing a real
  Dockerfile; not run before then.

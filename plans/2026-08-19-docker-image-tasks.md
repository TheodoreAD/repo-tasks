---
status: planned
updated: 2026-08-19
---

## Context

Goal includes building and pushing docker images reproducibly via `inv`, for a single image today
and multiple images in a monorepo later. Depends on
`plans/2026-08-19-monorepo-workspace-foundation.md` for the `[[docker]]` config entries (name, path,
dockerfile, image, group) and on `plans/2026-08-19-release-management.md` for the version string
used as the default image tag. Exercised for real by
`plans/2026-08-19-dogfood-sample-service.md`'s sample Dockerfile — this repo has no Dockerfile of
its own today.

Decisions from review:

- **Multi-arch:** single-arch by default (whatever architecture the build machine is — typically
  `amd64` on CI), with an optional `--platforms=linux/amd64,linux/arm64` argument that opts into
  `docker buildx` per invocation. Chosen over building around buildx unconditionally: multi-arch adds
  real setup cost (a `buildx create --use` builder bootstrap, QEMU cross-compilation emulation that
  can be 5–20x slower for compute-heavy build steps unless native-arch runners are used, and a
  `--push`-only constraint — buildx can't `--load` a multi-platform result into local `docker images`
  the way single-platform builds can) with no current concrete cross-arch deployment target driving
  it. Keeping the flag optional avoids a later rework if that need shows up.
- **Auth:** caller's responsibility for v1 (`docker login` already done, matching `quality.py`'s
  no-secrets-touched stance) — but automatic re-auth-on-failure stays in this plan for a later phase
  (Design §4) rather than being dropped, so the release flow doesn't quietly become more manual than
  it needs to be as more registries/consumers are added.
- **Tag scheme:** driven by `monorepo-workspace-foundation.md`'s grouped/hybrid versioning model — an
  image tags from its own group's version (shared with its paired Helm chart when one exists), not a
  whole-repo version and not fully independent of anything else in its group.

## Design

### 1. `src/repo_tasks/docker.py`

- `build(c, project=None, tag=None, platforms=None)`
  - No `platforms` → `docker build -t <image>:<tag> -f <dockerfile> <path>`.
  - `platforms` given → `docker buildx build --platform <platforms> -t <image>:<tag> -f <dockerfile>
    <path> --push`. The docstring must call out that multi-platform builds push as part of `build`
    itself (buildx's own `--load` limitation), so callers don't expect a separate `push` step to work
    for the multi-arch path.
- `push(c, project=None, tag=None)` — `docker push <image>:<tag>` (single-arch path only).
- `release(c, project=None)` — build then push, tagged with the resolved group's current version
  (from `version.py` once `release-management.md` lands) plus `latest`.
- `--tag` on `build`/`push` overrides the default for ad hoc/throwaway builds without touching the
  version-derived tag.

### 2. Config

Registry and image name come from `repo-tasks.toml`'s `[[docker]]` entries (`name`, `path`,
`dockerfile`, `image`, optional `group`) — see `monorepo-workspace-foundation.md` Design §2–3. Never
hardcoded in `docker.py` itself, keeping the task _logic_ identical across every consumer repo (the
README's stated design goal) even though registry/image-name legitimately differs per repo.

No-op cleanly when `repo-tasks.toml` has zero `[[docker]]` entries, matching
`quality.shell_check`'s existing "no shell scripts in this repo" pattern.

### 3. Multi-arch (`--platforms`)

Out-of-the-box behavior stays single-arch and simple. `--platforms` is accepted from v1 but exercises
the buildx path only when explicitly passed — no builder bootstrap, no QEMU cost, no `--push`-only
constraint on the common path.

### 4. Auth — deferred, not dropped

Phase 2 (not blocking this plan's v1, but written down so it isn't silently forgotten): on a clear
auth failure (`docker push` output containing `401`/`unauthorized`), `docker.py` attempts one
automatic re-auth cycle before failing outright:

- Resolve credentials via python's `keyring` package (cross-platform binding to macOS Keychain /
  GNOME Keyring-libsecret / Windows Credential Locker) if a matching entry exists for that registry.
- Otherwise fall back to whatever the platform's already-configured docker credential helper or SSO
  session provides (`docker-credential-ecr-login`, `docker-credential-gcloud`, an already-active
  `aws sso login`/`gcloud auth login` session, etc.).
- `repo-tasks` only orchestrates the retry — it never stores, generates, or invents credentials
  itself, and the retry logic here is shared (not duplicated) with `helm-chart-tasks.md`'s Design §4,
  which needs the identical behavior for `helm push`.

## Files touched

- `src/repo_tasks/docker.py` (new)
- `repo-tasks.toml` `[[docker]]` entry (added when `dogfood-sample-service.md`'s sample Dockerfile
  lands)
- Phase 2 auth: a shared `src/repo_tasks/_registry_auth.py` helper used by both `docker.py` and
  `helm.py`

## Verification

- Unit tests mocking `c.run` for `build`/`push`/`release` command construction — tag resolution,
  `--platforms` presence/absence, `--tag` override.
- Real build/push exercised manually against `dogfood-sample-service.md`'s Dockerfile once it exists.

---
status: planned
updated: 2026-08-19
---

## Context

Monorepo goal includes Helm charts alongside python/docker projects — one chart per deployable
service. Depends on `plans/2026-08-19-monorepo-workspace-foundation.md` for the `[[helm]]` config
entries and grouping model, and on `plans/2026-08-19-release-management.md` for the version a chart
gets bumped to. Exercised for real by `plans/2026-08-19-dogfood-sample-service.md`'s sample chart,
paired with that plan's sample docker image under one shared `group`.

Helm's own OCI support is straightforward and current: `helm push <chart>.tgz oci://<registry>/path`
uploads a chart packaged with `helm package`; auth follows the same `helm registry login` flow as
Docker registry auth; works against any OCI registry (GHCR, ECR, GAR, Harbor, Quay, Artifactory).

Decision from review: this repo will get its own dogfood Dockerfile + Helm chart
(`dogfood-sample-service.md`), so this plan is no longer purely forward-looking — it has a concrete
near-term exerciser, same as the docker plan.

## Design

### 1. `src/repo_tasks/helm.py`

- `lint(c, chart=None)` — `helm lint <path>`.
- `package(c, chart=None)` — `helm package <path>`.
- `push(c, chart=None, registry=None)` — `helm push <chart>.tgz oci://<registry>`.

### 2. Config

Chart entries come from the same `repo-tasks.toml` file `monorepo-workspace-foundation.md`
introduces for docker images — a `[[helm]]` array-of-tables with `name`, `path`, `registry`, optional
`group`. No-op cleanly with zero `[[helm]]` entries, matching `quality.shell_check`'s existing
pattern and `docker-image-tasks.md`'s equivalent no-op behavior.

### 3. Grouped version bump

Chart version is written by `version.py` as part of its group's bump (`Chart.yaml`'s
`version`/`appVersion`) — no separate helm-specific version flow. For the dogfood sample, the chart
and its paired docker image share `group = "sample-service"`, so a single `inv version.bump
--group=sample-service --part=minor` updates both together in one commit+tag, per
`monorepo-workspace-foundation.md` Design §3 and `release-management.md` Design §1.

### 4. Auth — deferred, shared with docker-image-tasks.md

Same Phase 2 design as `docker-image-tasks.md` Design §4: on a clear `helm push` auth failure,
attempt one automatic re-auth cycle via `keyring`-resolved credentials or the platform's already
-configured SSO/credential-helper flow, using the shared `src/repo_tasks/_registry_auth.py` helper
rather than a second, duplicated implementation.

## Files touched

- `src/repo_tasks/helm.py` (new)
- `repo-tasks.toml` `[[helm]]` entry (added when `dogfood-sample-service.md`'s sample chart lands)
- Shares `src/repo_tasks/_registry_auth.py` with `docker-image-tasks.md` (Phase 2, not this plan's
  first landing)

## Verification

- Unit tests mocking `c.run` for `lint`/`package`/`push` command construction.
- Real lint/package/push exercised manually against `dogfood-sample-service.md`'s sample chart once
  it exists.

---
status: landed
updated: 2026-08-23
---

## Context

Helm charts alongside python projects and docker images — one chart per deployable service, its
`appVersion` bumped in lockstep with the image it wraps. `helm.py`, `[[helm]]` discovery, and the
chart fields in the group bump landed 2026-08-23; the real-chart verification that kept this plan
open landed the same day with `plans/2026-08-19-dogfood-sample-service.md`'s sample chart.

## What landed

- `src/repo_tasks/helm.py` — `lint`/`package`/`push`, plus `--plain-http` on `push` (added when the
  integration round trip hit helm's lack of a loopback insecure-registry exemption).
- `src/repo_tasks/projects.py` — `HelmChart`/`discover_helm_charts`, reading `[[helm]]` entries with
  optional `registry`, optional `group`, and deliberately no zero-config fallback.
- `src/repo_tasks/version.py` — two `[[tool.bumpversion.files]]` blocks per chart sharing the bumped
  group.
- `repo-tasks.toml` — the real `[[helm]]` entry for the dogfood chart.

Verification is complete: `helm lint`/`package`/`push` all run against a real chart in
`tests/integration/test_dogfood_sample_service.py`, and a real group bump writes a real
`Chart.yaml`'s `version` and `appVersion` in `tests/integration/test_version_integration.py` — which
is what the plan's last `[UNVERIFIED:]` was waiting on.

## Migrated to

- **Code, tests, and README** — the module contract (task names, flags, `dist/helm/` output,
  no-op-on-zero-charts behaviour) lives in `src/repo_tasks/helm.py`, `tests/test_helm.py`, and
  README's "helm: lint, package, and push a chart" section. The three landing-time `[DECISION:]`
  notes are settled and visible in the code they describe: `--project` (not `--chart`) matching
  every other module, `dist/helm/` as the package destination, and `push` deriving the `.tgz`
  filename from the group's current version rather than parsing `Chart.yaml`.
- [`contributing/versioning.md`](../contributing/versioning.md) — why `push` reads the version
  rather than parsing the chart (the read side of the single-writer rule), the consequence that a
  `[[helm]]` entry's `name` must match `Chart.yaml`'s, and the `Chart.yaml` formatting pitfalls.
- [`contributing/test-tiers.md`](../contributing/test-tiers.md) — the real-chart coverage and the
  `--plain-http` pitfall.
- `plans/2026-08-23-docker-no-op-alignment.md` (new) — the one live deferred item this plan was
  holding: `docker.py` raises where the convention now says no-op, unlike `helm.py`.
- `plans/2026-08-23-registry-auth-retry.md` (already open) — auth-failure handling for `helm push`
  and `docker push` together, including whether the automatic re-auth cycle is worth building at
  all. That plan was sequenced behind this one and is now unblocked.
- **Not migrated:** the no-zero-config-fallback rationale, which
  [`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)'s "Smart
  defaults" section and `discover_helm_charts`' own docstring already state.

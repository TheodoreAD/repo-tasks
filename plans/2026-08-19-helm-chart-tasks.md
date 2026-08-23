---
status: blocked on dogfood-sample-service.md's sample chart for real-world verification
updated: 2026-08-23
---

## Context

Monorepo goal includes Helm charts alongside python/docker projects — one chart per deployable
service. Depends on `plans/2026-08-19-monorepo-workspace-foundation.md` for the `[[helm]]` config
entries and grouping model, and on [`contributing/versioning.md`](../contributing/versioning.md) for
the version a chart gets bumped to. Exercised for real by
`plans/2026-08-19-dogfood-sample-service.md`'s sample chart, paired with that plan's sample docker
image under one shared `group`.

Helm's own OCI support is straightforward and current: `helm push <chart>.tgz oci://<registry>`
uploads a chart packaged with `helm package`; auth follows the same `helm registry login` flow as
Docker registry auth; works against any OCI registry (GHCR, ECR, GAR, Harbor, Quay, Artifactory).

Decision from review: this repo will get its own dogfood Dockerfile + Helm chart
(`dogfood-sample-service.md`), so this plan is no longer purely forward-looking — it has a concrete
near-term exerciser, same as the docker plan.

**2026-08-23: Design §1–§3 landed** (`helm.py`, `[[helm]]` discovery, chart fields in the group
bump), with the deviations from the original sketch recorded inline below. What keeps this plan open
is Verification's real-chart exercise, blocked on the dogfood chart existing.

## Design

### 1. `src/repo_tasks/helm.py`

- `lint(c, project=None)` — `helm lint <path>`.
- `package(c, project=None)` — `helm package <path> --destination dist/helm`.
- `push(c, project=None, registry=None)` — `helm push dist/helm/<name>-<version>.tgz <registry>`.

Landed 2026-08-23, with three deviations from the original sketch:

- [DECISION: the selection flag is `--project`, not the originally-sketched `--chart` —
  `monorepo-workspace-foundation.md` Design §4 already standardized per-task `--project` filtering
  across modules and `docker.py` shipped with it; a helm-only synonym would make consumers learn two
  names for the same axis.]
- [DECISION: `package` writes into `dist/helm/` rather than helm's cwd default — keeps the repo root
  clean and groups build output where `dist.py` already puts it. `dist.clean` wiping it is fine:
  repackaging is cheap and `helm package` overwrites.]
- [DECISION: `push` derives the `.tgz` filename from `current_version(c, group=chart.group)` — the
  read-side of versioning.md's single-writer rule — instead of parsing `Chart.yaml` (which would
  need a YAML dependency for stdlib-only code). Consequences: a `[[helm]]` entry's `name` must match
  `Chart.yaml`'s own `name`, and a chart whose `Chart.yaml` version drifted from its group's fails
  loudly at push time with a missing-file error rather than pushing the wrong thing.]

### 2. Config

Chart entries come from the same `repo-tasks.toml` file `monorepo-workspace-foundation.md`
introduces for docker images — a `[[helm]]` array-of-tables with `name`, `path`, optional `registry`
(only `push` insists on one, via its own flag or the entry), optional `group` (default: `name`).
Landed 2026-08-23 as `projects.discover_helm_charts(c) -> list[HelmChart]`.

No-op cleanly with zero `[[helm]]` entries, matching `quality.shell_check`'s existing pattern — each
task prints a short "nothing to do" note and returns; see
[`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)'s "No-op
cleanly when an artifact kind is absent". No zero-config fallback, unlike docker's
Dockerfile-at-root: a chart has no single canonical root location, and a pushable chart needs a
registry only explicit config can supply.

- [DEFERRED: `docker.py` predates the strict no-op form and raises with zero images discovered
  instead of no-opping the way `helm.py` now does — tolerable while nothing wires `docker.*` into a
  composite, worth aligning to `helm.py`'s print-and-return shape if that changes.
  `contributing/task-module-conventions.md` points here.]

### 3. Grouped version bump

Chart version is written by `version.py` as part of its group's bump (`Chart.yaml`'s
`version`/`appVersion`) — no separate helm-specific version flow. Landed 2026-08-23: `_bump`
resolves `discover_helm_charts` entries sharing the bumped group and appends two
`[[tool.bumpversion.files]]` blocks per chart to the generated config. The search patterns assume
`helm create`'s own scaffold quoting (`version:` unquoted, `appVersion:` quoted) — bump-my-version
fails loudly when a search string is absent, so a chart straying from that quoting breaks the bump
instead of half-applying it.

For the dogfood sample, the chart and its paired docker image share `group = "sample-service"`, so a
single `inv version.bump --group=sample-service --part=minor` updates both together in one
commit+tag, per `monorepo-workspace-foundation.md` Design §3 and
[`contributing/versioning.md`](../contributing/versioning.md)'s "Grouping: what bumps together".

- [UNVERIFIED: the chart half of a group bump has only unit coverage of the generated config — no
  real chart in any consumer repo has been bumped through bump-my-version yet. Phase 1's
  `_resolve_project` also still requires the group to name a python project, so a chart-only group
  (no python project sharing the name) can't bump or resolve `current_version` yet — the dogfood
  sample pairs its chart with a python project, so this only bites a future chart-only consumer.]

### 4. Auth — deferred, shared with docker

[DEFERRED: `helm push` auth-failure handling is not part of this plan's first landing. It is owned
by `plans/2026-08-23-registry-auth-retry.md`, which covers `docker push` and `helm push` together —
including the open question of whether the originally-designed automatic re-auth cycle is worth
building at all, or should reduce to detecting the failure and printing the exact
`helm registry login` command via `gitflow.py`'s `_next_steps()` convention. That plan is explicitly
sequenced behind this one; `helm.py` now exists, so it is unblocked.]

## Files touched

- `src/repo_tasks/helm.py` (new, landed) + `__init__.py` wiring
- `src/repo_tasks/projects.py` — `HelmChart`/`discover_helm_charts` (landed)
- `src/repo_tasks/version.py` — chart `[[tool.bumpversion.files]]` blocks in the generated group
  config (landed)
- `repo-tasks.toml` `[[helm]]` entry (added when `dogfood-sample-service.md`'s sample chart lands)
- Auth handling: none in this plan's first landing — see `plans/2026-08-23-registry-auth-retry.md`

## Verification

- Unit tests mocking `c.run` for `lint`/`package`/`push` command construction (done —
  `tests/test_helm.py`, plus discovery in `tests/test_projects.py` and the chart config blocks in
  `tests/test_version.py`).
- [UNVERIFIED: real `helm lint`/`package`/`push` and a real group bump touching `Chart.yaml` have
  not run against an actual chart — exercised once `dogfood-sample-service.md`'s sample chart
  exists. This is what the status line blocks on.]

---
status: in-progress
updated: 2026-08-23
---

## Context

`repo-tasks` currently ships one task module (`quality.py`): lint/format/type_check/shell_check/test
plus the `fix`/`check`/`precommit` composite. It assumes exactly one project living at the consumer
repo's root (this repo's own `src/repo_tasks` is the only exerciser so far, via `tasks.py`
dogfooding itself).

The broader goal is to add docker image build/push, python package build/push, gitflow branch flows,
and semver bumping. Most of that has since landed — `version.py`/`gitflow.py`
([`contributing/release-flow.md`](../contributing/release-flow.md),
[`contributing/versioning.md`](../contributing/versioning.md)), `docker.py`, `dist.py`, `venv.py`,
and `deps.py`
([`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)). The
siblings still open:

- `plans/2026-08-19-helm-chart-tasks.md`
- `plans/2026-08-19-dogfood-sample-service.md` (the concrete Dockerfile+chart pair that exercises
  this plan's grouping model and the docker/helm task modules for real)
- `plans/2026-08-22-pypi-publish-integration.md` / `plans/2026-08-22-docker-registry-integration.md`
  (the real test.pypi.org/pypi.org and GHCR wiring `dist.py`/`docker.py` eventually publish to)

All of them need the same thing this plan provides: a way for a task module to answer "what
project(s) exist in this consumer repo, where, what kind (python package / docker image / helm
chart), and which of them release together as one unit?" — for a single-project repo today, and for
a monorepo with several `src`-layout projects plus Helm charts later.

Versioning-model decision that shapes this plan's schema: independent per-project versions/tags,
_except_ a docker image and its own Helm chart (the chart that wraps that specific image) bump
together as one group, since a chart's `appVersion` is meaningless independent of the image it
deploys. Full comparison against fixed/lockstep and fully-independent alternatives lives in this
plan's design history; the grouping mechanism it requires is specified in Design §3 below.

Build order: land this plan's Phase 1 (single-project fallback, zero new config) alongside the first
version-bumping work, since bumping needs _some_ project to bump immediately. (Both have since
landed.) Docker/python-package/helm tasks can each land independently after that, in any order,
since they only read from whatever discovery this plan provides. Multi-project (Phase 2)
generalization comes once `dogfood-sample-service.md` gives it a real second project to resolve.

## Design

### 1. Python project discovery (`src/repo_tasks/projects.py`)

Reuses `uv`'s own workspace mechanism as the source of truth for python projects instead of
inventing a parallel manifest for something `uv` already models well.

- **Phase 1 (land now):** no `[tool.uv.workspace]` present in the consumer's root `pyproject.toml` →
  the repo root's own `[project]` table _is_ the one implicit project.
  `discover_python_projects(c)
  -> list[PythonProject]` (dataclass: `name`, `path`, `version`)
  returns a single entry. This must keep working with zero new config — it's the common case, and
  the current zero-config ergonomics (README: "That's the entire file — no local override") must not
  regress.
- [DEFERRED: Phase 2 — resolve each `[tool.uv.workspace].members` glob's own `pyproject.toml` into
  its own `PythonProject`. Blocked on a real multi-member consumer existing at all, i.e. on
  `plans/2026-08-19-dogfood-sample-service.md`. This is the single item keeping this plan
  `in-progress`; Phase 1 landed.]
- Every later task module (`docker.py`, `python_pkg.py`, `helm.py`, `version.py`) calls this instead
  of hardcoding "the repo root."

### 2. `repo-tasks.toml` for non-python artifacts

Docker images and Helm charts aren't modeled by `uv` workspaces at all, so they get their own small
dedicated config file — consistent with this repo's stated design ("each tool gets its own dedicated
config file... not consolidated into pyproject.toml", README.md "Design") and distinct from
`pyproject.toml`, which is where python-project data (`[tool.uv.workspace]`, each member's own
`[project].version`) unavoidably has to live instead.

```toml
[[docker]]
name = "sample-service"
path = "examples/sample-service"
dockerfile = "examples/sample-service/Dockerfile"
image = "ghcr.io/org/sample-service"
group = "sample-service"

[[helm]]
name = "sample-service-chart"
path = "examples/sample-service/chart"
registry = "oci://ghcr.io/org/charts"
group = "sample-service"
```

An absent file or empty arrays means zero images/charts. Every task that reads it must no-op cleanly
— the same pattern `quality.shell_check` already uses for "no `*.sh` files in this repo," safe to
wire unconditionally into a future top-level composite without a per-repo opt-out.

**2026-08-21 (landed, docker half):** `[[docker]]` reading landed as
`projects.discover_docker_images(c)
-> list[DockerImage]`, with one addition beyond the original
design: when `repo-tasks.toml` is absent or has no `[[docker]]` entries, a `Dockerfile` at the repo
root is treated as one implicit image — same zero-config ergonomics as Design §1's Phase 1
python-project fallback (per review: "make sure there is also some smart default for the most basic
cases"). It's named after the repo's python project (so `group` naturally matches for version
resolution), or the repo directory's own name if there's no `pyproject.toml`; `image` defaults to
that same name as a local-only placeholder. See
[`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)'s "Smart
defaults, so zero config is a real option" for `docker.py`'s side of this.

**2026-08-23 (landed, helm half):** `[[helm]]` reading landed as
`projects.discover_helm_charts(c) -> list[HelmChart]` with `plans/2026-08-19-helm-chart-tasks.md`.
Two schema refinements against the sketch above: `registry` is optional (only `helm.push` insists on
one) and there is deliberately no zero-config fallback, unlike docker's Dockerfile-at-root — that
plan records why.

### 3. Grouping for shared version/tag tracks

Optional `group` key on `[[docker]]` and `[[helm]]` entries (python projects get an implicit group
equal to their own `name` unless a future need arises to override it). Entries sharing a `group`
value are bumped and tagged together by `version.py`
([`contributing/versioning.md`](../contributing/versioning.md)) as one unit — e.g. a service's
docker image and its Helm chart share `group = "sample-service"` and release in lockstep, while an
unrelated shared python library elsewhere in the repo keeps its own independent version, untouched
by that release.

An entry with no `group` key defaults to being its own independent group (`group == name`) — this is
the ordinary case for a standalone project with no paired image/chart.

### 4. `--project` filtering

Per-task CLI flag only (e.g. `inv docker.build --project=sample-service`), no config-level default.
Default with no flag = act on every discovered entry. Simpler, matches invoke's own idiom; a
config-level default list can be added later if repeatedly passing `--project` in practice proves
annoying.

### 5. Distribution model

`repo-tasks` stays an external git dependency only
(`uv add --dev
git+https://github.com/TheodoreAD/repo-tasks`) — no vendoring/forking scenario to
design around. This doesn't change any discovery logic here, but confirms `repo-tasks.toml` and
`projects.py` only ever need to reason about _the consumer's_ workspace root, never a copy of
`repo-tasks` living inside it.

## Files touched

- `src/repo_tasks/projects.py` — `discover_python_projects`/`PythonProject` (landed), plus
  `discover_docker_images`/`DockerImage` (landed 2026-08-21, docker half of Design §2).
- `repo-tasks.toml` — this repo's own copy still doesn't exist; not needed until
  `dogfood-sample-service.md`'s Dockerfile lands (the zero-config default covers it until then).
- `pyproject.toml` — unchanged for Phase 1; Phase 2 adds `[tool.uv.workspace]` once
  `dogfood-sample-service.md` introduces a second workspace member.

## Verification

- Unit tests for `projects.py`'s single-implicit-project fallback, run against this repo's own
  `src/repo_tasks` (mirrors `tests/test_quality.py`'s existing `MockContext`/`Result` style).
- Phase 2: a `tests/fixtures/` throwaway workspace fixture exercising multi-member glob resolution,
  added once Phase 2 actually lands — separate from the real `dogfood-sample-service.md` example so
  discovery logic has a minimal, fast-to-run test case independent of any real Dockerfile/chart.

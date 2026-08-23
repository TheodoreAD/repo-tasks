---
status: landed
updated: 2026-08-23
---

## Context

Every task module needed one answer to "what project(s) exist in this consumer repo, where, what
kind, and which of them release together as one unit?" — for a single-project repo today and a
monorepo later. Phase 1 (the single implicit project, zero new config) landed alongside the first
version-bumping work; Phase 2 (workspace-member resolution) landed 2026-08-23 once
`plans/2026-08-19-dogfood-sample-service.md` gave it a real second project to resolve.

## What landed

- `projects.discover_python_projects(c)` resolves the root `[project]` table first, then each
  `[tool.uv.workspace]` `members` glob's own `pyproject.toml`, honouring `exclude`. `uv`'s workspace
  table is the source of truth — no parallel manifest. A table-less ("virtual") root is tolerated,
  since uv allows one.
- Root-first ordering, load-bearing: `dist.py` and `version.py` index `[0]` as "the repo's own
  project", so adding a member never changes what a no-flag invocation acts on.
- `projects.discover_docker_images(c)`/`discover_helm_charts(c)` reading `repo-tasks.toml`'s
  `[[docker]]`/`[[helm]]` entries, with the `group` key tying artifacts into one release unit.
- `--project` filtering that actually selects, across `dist.py`, `venv.py`, `docker.py`, `helm.py`.

Design §5's distribution model (external git dependency only, never vendored) held and needed no
code: `projects.py` only ever reasons about the consumer's own workspace root.

## Migrated to

- **Code, tests, and README** — discovery lives in `src/repo_tasks/projects.py` with
  `tests/test_projects.py` covering both phases; README's "monorepos: workspace members, version
  groups, and the sample service" section is the usage-facing home for the workspace table, the
  `repo-tasks.toml` schema, and what a `group` means. The distribution model is already stated in
  README's "Installing".
- [`contributing/versioning.md`](../contributing/versioning.md) — the grouping model itself, and the
  constraint the dogfood surfaced: a group's version has to live in some python project's
  `pyproject.toml`, so a chart-only or image-only group cannot resolve one yet.
- [`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md) — "Smart
  defaults, so zero config is a real option" (both fallbacks), that ambiguity is an error rather
  than a guess, and that a `--project` flag must actually select rather than being accepted and
  discarded.
- **Not migrated:** Verification's planned `tests/fixtures/` throwaway workspace tree. The Phase 2
  tests build their minimal workspaces in `tmp_path` instead — same isolation from the real
  `examples/` sample, no committed fixture tree to keep in sync, and it matches how every other
  discovery test in that module already works.

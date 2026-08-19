---
status: idea
updated: 2026-08-19
---

## Context

`plans/2026-08-19-docker-image-tasks.md` and `plans/2026-08-19-helm-chart-tasks.md` both need a real
Dockerfile and Helm chart to exercise against — unit tests can mock `c.run`, but only a real artifact
proves `docker build`/`docker push`/`helm lint`/`helm package`/`helm push` actually work end to end.
`plans/2026-08-19-monorepo-workspace-foundation.md`'s grouped/hybrid versioning model
(`plans/2026-08-19-release-management.md` Design §1) also needs a concrete pair of artifacts that
share one `group` to prove a single version bump actually updates both together.

Decision from review: add exactly this — a minimal sample Dockerfile + matching Helm chart, living
in this repo, purely to dogfood the docker/helm/version-grouping task modules against something real.

## Open questions

[NEEDS CLARIFICATION: what should the sample app actually do? A trivial stdlib-only HTTP server
(e.g. Python's `http.server`) is probably enough to prove the Dockerfile/chart round-trip end to end.
Does it need to demonstrate more — e.g. actually importing `repo_tasks` itself, to prove the
monorepo's own python package can be a dependency of another project living in the same repo once
Phase 2 workspace support exists?]

[NEEDS CLARIFICATION: where does it live? Two options: (a) become a real `[tool.uv.workspace]` member
immediately (e.g. `examples/sample-service/` with its own `pyproject.toml`), turning `repo-tasks`
into an actual (if minimal) monorepo right away; or (b) start as a bare `Dockerfile` + `chart/` pair
with no python component at all, deferring the workspace-member step until
`monorepo-workspace-foundation.md`'s Phase 2 is actually being built. Leaning toward (b) — keep it
docker+helm-only first, added as soon as those two task modules land, and only fold it into a real
workspace member later when Phase 2 needs a concrete second project to resolve against.]

[NEEDS CLARIFICATION: registry target for the dogfood push — a real registry (GHCR under the same
GitHub account/org as this repo) so the round trip is fully real, or a local-only/throwaway registry
(e.g. a `registry:2` container) so nothing is ever actually pushed publicly? Affects whether this
plan needs any CI credentials at all, or stays entirely local-dev-only.]

## Recommended direction

- Add `examples/sample-service/Dockerfile` (exact path per the open question above) wrapping a
  minimal stdlib-only HTTP server — no new runtime dependency for the sample itself, trivial to
  reason about and keep working.
- Add a matching `examples/sample-service/chart/` Helm chart wrapping that image, with `Chart.yaml`
  paired via `group = "sample-service"` against the same-named `[[docker]]` entry in
  `repo-tasks.toml`.
- Land only after `docker-image-tasks.md` and `helm-chart-tasks.md` are themselves implemented —
  this plan exists to exercise them, not to block them.
- Once built, becomes the running example referenced by both of those plans' Verification sections,
  and the first real multi-artifact case for `monorepo-workspace-foundation.md`'s grouping model.

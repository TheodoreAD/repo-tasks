---
status: idea
updated: 2026-08-23
---

## Context

`docker.py` (landed) and `plans/2026-08-19-helm-chart-tasks.md` both need a real Dockerfile and Helm
chart to exercise against — unit tests can mock `c.run`, but only a real artifact proves
`docker build`/`docker push`/`helm lint`/`helm package`/`helm push` actually work end to end.
`plans/2026-08-19-monorepo-workspace-foundation.md`'s grouped/hybrid versioning model
([`contributing/versioning.md`](../contributing/versioning.md)'s "Grouping: what bumps together")
also needs a concrete pair of artifacts that share one `group` to prove a single version bump
actually updates both together.

Decision from review: add exactly this — a minimal sample Dockerfile + matching Helm chart, living
in this repo, purely to dogfood the docker/helm/version-grouping task modules against something
real.

`plans/2026-08-22-docker-registry-integration.md` is what eventually pushes this Dockerfile's image
to a real registry (GHCR) once it exists — that plan's auth/CI wiring can land independently, but
its actual `docker.release` verification is blocked on this plan.

## Open questions

[NEEDS CLARIFICATION: what should the sample app actually do? A trivial stdlib-only HTTP server
(e.g. Python's `http.server`) is probably enough to prove the Dockerfile/chart round-trip end to
end. Does it need to demonstrate more — e.g. actually importing `repo_tasks` itself, to prove the
monorepo's own python package can be a dependency of another project living in the same repo once
Phase 2 workspace support exists?]

[NEEDS CLARIFICATION: where does it live? Two options: (a) become a real `[tool.uv.workspace]`
member immediately (e.g. `examples/sample-service/` with its own `pyproject.toml`), turning
`repo-tasks` into an actual (if minimal) monorepo right away; or (b) start as a bare `Dockerfile` +
`chart/` pair with no python component at all, deferring the workspace-member step until
`monorepo-workspace-foundation.md`'s Phase 2 is actually being built. Leaning toward (b) — keep it
docker+helm-only first, added as soon as those two task modules land, and only fold it into a real
workspace member later when Phase 2 needs a concrete second project to resolve against.]

[NEEDS CLARIFICATION: registry target for the dogfood push — a real registry (GHCR under the same
GitHub account/org as this repo) so the round trip is fully real, or a local-only/throwaway registry
(e.g. a `registry:2` container) so nothing is ever actually pushed publicly? Affects whether this
plan needs any CI credentials at all, or stays entirely local-dev-only.]

[PITFALL: GHCR rejects any uppercase character in an image ref — confirmed 2026-08-23 by
`plans/2026-08-22-docker-registry-integration.md`'s auth smoke test. This account's GitHub username
is `TheodoreAD` (mixed case), so whatever `[[docker]]`/`[[helm]]` `image`/`registry` value this plan
eventually writes into `repo-tasks.toml` must lowercase the owner segment
(`ghcr.io/theodoread/sample-service`, not `.../TheodoreAD/...`), or the push fails outright.]

## Recommended direction

- Add `examples/sample-service/Dockerfile` (exact path per the open question above) wrapping a
  minimal stdlib-only HTTP server — no new runtime dependency for the sample itself, trivial to
  reason about and keep working.
- Add a matching `examples/sample-service/chart/` Helm chart wrapping that image, with `Chart.yaml`
  paired via `group = "sample-service"` against the same-named `[[docker]]` entry in
  `repo-tasks.toml`.
- Land only after `helm.py` is implemented (`docker.py` already is) — this plan exists to exercise
  those modules, not to block them.
- Once built, becomes the running example referenced by both of those plans' Verification sections,
  and the first real multi-artifact case for `monorepo-workspace-foundation.md`'s grouping model.

[DEFERRED: when this plan's Dockerfile is actually written, it should follow the multi-stage recipe
this repo already settled on — deps-only builder layer (bind-mount just `uv.lock`+`pyproject.toml`,
`inv venv.sync --no-install-project`, so the layer cache survives every commit that touches
neither), then `inv dist.build` + `inv venv.install_wheel` on top, and a final stage that copies
only `.venv` onto a fresh base as a non-root user with no source tree and no `uv` binary. Adapted
from Astral's own [`uv-docker-example`](https://github.com/astral-sh/uv-docker-example)
`multistage.Dockerfile`. README's `venv`/`deps` section is its single home — write the Dockerfile
against that rather than restating the recipe here, which would be a third copy. Carried over from
the now-retired `plans/2026-08-20-venv-deps-tasks.md` §6.]

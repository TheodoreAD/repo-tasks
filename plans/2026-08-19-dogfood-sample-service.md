---
status: landed
updated: 2026-08-23
---

## Context

`docker.py` and `helm.py` both needed a real Dockerfile and Helm chart to exercise against — unit
tests can mock `c.run`, but only a real artifact proves
`docker build`/`docker push`/`helm
lint`/`helm package`/`helm push` work end to end. The grouped
versioning model ([`contributing/versioning.md`](../contributing/versioning.md)'s "Grouping: what
bumps together") needed a concrete pair of artifacts sharing one `group` to prove a single bump
updates both.

Landed 2026-08-23 as `examples/sample-service/` — a stdlib-only HTTP service that is simultaneously
a `[tool.uv.workspace]` member, the `[[docker]]` image built by a multi-stage Dockerfile, and the
`[[helm]]` chart that deploys it, all under `group = "sample-service"`.

## What the open questions resolved to

- **What the app does:** a stdlib-only `http.server` answering `/` and `/healthz`, zero runtime
  dependencies. It reports its version from installed distribution metadata rather than a
  `__version__` constant, which makes "the container runs the wheel that was built for it" an
  assertable fact rather than an assumption.
- **Where it lives:** a real workspace member immediately (option (a)), not the docker+helm-only
  start the plan had been leaning toward. The leaning turned out not to be implementable: a group's
  version resolves through a _python project_ (`version.py`'s `_resolve_project`), so an image+chart
  pair grouped under a name no python project answers to cannot resolve `current_version` at all.
  The settled multi-stage Dockerfile recipe is a python-package recipe too, so a bare `Dockerfile` +
  `chart/` pair could not have followed it. Recorded permanently in
  [`contributing/versioning.md`](../contributing/versioning.md)'s "Grouping" section.
- **Registry target:** the local `registry:3` container the integration tier already runs, for the
  automated round trip. The real GHCR push stays owned by
  `plans/2026-08-22-docker-registry-integration.md`; this plan's `image =` value is the real GHCR
  ref (lowercased owner) so that plan has nothing left to change.

## Migrated to

- **Code, tests, and README** — the sample itself (`examples/sample-service/`), its
  `repo-tasks.toml` entries, and the integration coverage
  (`tests/integration/test_dogfood_sample_service.py`,
  `tests/integration/test_version_integration.py`). README's "monorepos: workspace members, version
  groups, and the sample service" section is the usage-facing home; its venv/deps section already
  owns the multi-stage recipe the Dockerfile follows, so the recipe is not restated anywhere.
- [`contributing/versioning.md`](../contributing/versioning.md) — that a group's version must live
  in some python project's `pyproject.toml`, plus the two `Chart.yaml` formatting pitfalls (a
  formatter rewriting the quoting breaks the bump; `helm package` re-serializes the file into the
  archive).
- [`contributing/test-tiers.md`](../contributing/test-tiers.md) — what the dogfood round trip
  covers, `helm push`'s `--plain-http` requirement against a TLS-less registry, and the
  `testcontainers` import that makes the whole integration directory uncollectable without the
  group.
- [`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md) — that a
  `--project` flag must actually select, and that invoke's `pre=` drops the caller's arguments.
- **Not migrated:** the GHCR uppercase pitfall this plan carried a copy of. It already lives on
  `plans/2026-08-22-docker-registry-integration.md`, which owns registry auth, and on the
  `[[docker]]` entry in `repo-tasks.toml` where it actually bites. A third copy would have to be
  kept in sync with two others.
- **Not migrated:** the multi-stage recipe's own contents, deliberately. README's venv/deps section
  is its single home; `examples/sample-service/Dockerfile` is the worked instance.

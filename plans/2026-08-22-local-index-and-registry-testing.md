---
status: planned
updated: 2026-08-22
---

## Context

`dist.py` (build/publish/versions) and `docker.py` (build/push/release) are both landed, but only
unit-tested with mocked `c.run`/`urllib` — no test exercises a real package upload+query round
trip or a real image push. Mirrors the `db-defaults` skill's philosophy for this repo's own test
infrastructure: permissively-licensed, actively-maintained, low-boilerplate, testable fully inside
a plain `pytest` run with no cloud account needed — with one deliberate departure from its usual
"no Docker" criterion: since `docker.py`'s actual subject under test _is_ Docker, a running local
Docker daemon is unavoidably required here. That's still "local," just not "no Docker."

Two sibling plans cover the _real_ external services this one deliberately doesn't touch —
`plans/2026-08-22-pypi-publish-integration.md` (real test.pypi.org/pypi.org) and
`plans/2026-08-22-docker-registry-integration.md` (real GHCR) — both occasional,
manual/CI-triggered flows (rate limits, real secrets, irreversible side effects), not something
run on every `inv quality.test`. This plan is the fast, hermetic, run-every-time local stand-in for
both, so `dist.py`/`docker.py`'s actual network/upload logic gets real integration coverage without
ever touching anything external.

Tool choices below are the result of real research (not guessed), done specifically for this plan:
license, current maintenance activity, and — critically — whether each candidate actually exercises
`dist.py`'s two distinct code paths (PEP 691 JSON _and_ PEP 503 HTML fallback) rather than just one.

## Design

### 1. Local package index: `devpi-server`, not `pypiserver`

`pypiserver` (MIT/zlib, actively maintained — 2.4.1 released 2026-02-10) was the more obvious
first choice, but its `CHANGES.rst` confirms it has never added PEP 691 JSON Simple API support —
only the PEP 503 HTML index. Testing `dist.versions()` against it would only ever exercise the
HTML-fallback branch, leaving the JSON branch (the primary path against any modern index,
including real PyPI) completely untested.

`devpi-server` (MIT, actively maintained — 6.20.3 stable 2026-06-30) serves both: PEP 691 JSON on
its own `/simple` endpoint (added per
[devpi/devpi#986](https://github.com/devpi/devpi/issues/986), now closed/shipped) and PEP 503 HTML
for non-JSON-aware clients — the one local server that can exercise both of `dist.py`'s branches
against something real. A third option, `simple-repository-server`, does PEP 691 only via a
`?format=...` querystring rather than real `Accept`-header content negotiation, so it wouldn't
exercise `dist.py`'s actual `_get(url, accept=...)` code path — not used.

No dedicated pytest fixture plugin is depended on (`pytest-devpi-server` exists in the
`man-group/pytest-plugins` monorepo, but that repo's maintenance freshness wasn't confirmed —
verify before ever reaching for it). Hand-roll instead, matching `db-defaults`' low-boilerplate
bias: a `tmp_path`-scoped fixture that launches `devpi-server` as a subprocess pointed at a scratch
server-dir + free port, polls until it's up, uses the `devpi-client` CLI to init a local
user/index, yields the base URL, and terminates the subprocess on teardown.
[NEEDS CLARIFICATION: devpi's exact upload/simple URL path shape (`/<user>/<index>/...`) and the
precise `devpi-client` init/upload invocations — couldn't be pulled from docs via WebFetch
(redirects/thin pages), confirm directly via `devpi-server --help`/`devpi init --help` at
implementation time.]

### 2. Local docker registry: `registry:3` via `testcontainers-python`

`registry:3` (Docker's own open-source
[Distribution](https://github.com/distribution/distribution) registry, Apache-2.0, actively
maintained — the same engine behind Docker Hub/GHCR/GitLab Registry/Harbor; `registry:2` still
works but `registry:3` is Docker Hub's own current quick-start tag) runs open/insecure by default
with no auth or TLS — Docker's own deploy docs call this "only appropriate for testing," which is
exactly this use case.

`testcontainers` (PyPI, Apache-2.0, very actively maintained — latest release 2026-07-24) provides
the fixture shape instead of hand-rolling one against the `docker` SDK directly — its built-in
`ryuk`-based auto-cleanup (no leaked containers even on a crashed test run) is real boilerplate a
hand-rolled fixture would have to reimplement (port allocation, readiness polling, teardown-on-
failure), unlike some `db-defaults` categories where the stdlib/simple option won outright:

```python
from testcontainers.core.container import DockerContainer

with DockerContainer("registry:3").with_exposed_ports(5000) as registry:
    port = registry.get_exposed_port(5000)
    # docker.py's build/push point at f"127.0.0.1:{port}/<image>:<tag>"
```

[NEEDS CLARIFICATION: this exact snippet shape is standard `testcontainers` core API
(`with_exposed_ports`/`get_exposed_port`, used internally by every bundled module like
`PostgresContainer`) but wasn't found verbatim on the registry-specific docs page — verify against
the actual installed package at implementation time.]

**Gotcha to document, not just assume:** push/pull against `127.0.0.1:{port}/...` explicitly, never
`localhost`. Docker's `127.0.0.0/8` auto-insecure-registry exemption (since Engine 1.3.2) reliably
covers literal `127.0.0.1`, but Docker's own docs warn not to rely on it long-term, and it isn't
guaranteed to extend to the `localhost` hostname identically on every platform (Docker Desktop on
macOS/Windows can differ from Linux `dockerd`). Document the `daemon.json`
`{"insecure-registries": ["127.0.0.1:<port>"]}` fallback for a machine that doesn't get the
automatic exemption, rather than silently assuming it always works.

### 3. Wiring into pytest as a separate, opt-in tier

Both fixtures require an external prerequisite (`devpi-server` installed, a reachable Docker
daemon) that a plain `inv quality.test` run today assumes nothing beyond the dev dependency group.
Keep them a distinct, explicitly-marked tier — a `tests/integration/` directory, collected only via
a new `quality.test_integration` task (or `inv quality.test --integration`, whichever reads more
consistently with this repo's existing flag style once it's actually being written) — rather than
folding them into the default `quality.test`/`quality.check`/`quality.precommit` composite, so nobody's
plain `inv quality.precommit` starts silently requiring Docker. Each fixture skips gracefully
(`pytest.skip`, not a hard failure) when its prerequisite is missing (`shutil.which("devpi-server")`,
a Docker-daemon reachability check) — GitHub Actions runners ship Docker preinstalled, so CI can
opt in by additionally `pip install`-ing `devpi-server`/`devpi-client` for that one job.

### 4. What gets exercised

- `dist.py`: `build` → `publish` (real, non-dry-run upload against the local devpi index) →
  `versions` round trip, with one dedicated test forcing the HTML-fallback branch (bypass/strip the
  JSON `Accept` header) so both of `dist.py`'s parsing paths get real coverage, not just whichever
  one devpi happens to answer with by default.
- `docker.py`: `build` → `push` round trip against the local registry, image name pointed at
  `127.0.0.1:{port}/...` via a test-only override (constructing a `DockerImage` directly, not
  through `repo-tasks.toml` or the zero-config default) so this test doesn't depend on a real
  Dockerfile existing in this repo yet.

## Files touched

- `tests/conftest.py` or `tests/fixtures/` (new) — the two hand-rolled fixtures.
- `tests/integration/test_dist_integration.py`, `tests/integration/test_docker_integration.py`
  (new).
- `pytest.ini` — marker registration and/or `testpaths` adjustment so the default collection run
  excludes `tests/integration/` unless opted in.
- `src/repo_tasks/quality.py` — new `test_integration` task (or a flag on the existing `test`),
  deliberately _not_ added to `check`/`precommit`'s `pre=[...]`.
- `pyproject.toml` — `devpi-server`, `devpi-client`, `testcontainers` added to a dedicated
  optional/dev-only group (not the base `dev` group every consumer's `inv dev-env.setup` installs,
  since only this repo's own contributors need them) — exact grouping mechanism to confirm at
  implementation time (`uv`'s dependency-groups support arbitrary named groups beyond `dev`).
- `README.md`/`AGENTS.md` — note on running the integration tier locally and its Docker/devpi-server
  prerequisites.

## Verification

- Both fixtures start and tear down cleanly in isolation (a trivial "does the server answer" test
  each).
- The two integration test files pass locally when Docker and `devpi-server` are both available.
- `inv quality.test`/`quality.precommit` (the default, everyday path) stays exactly as fast as
  today and requires neither Docker nor `devpi-server` — confirmed by running it on a machine/
  container with neither installed and seeing a clean pass, not a skip-related failure.
- A machine lacking either prerequisite sees the integration tests skip with a clear, specific
  reason string — never a hard failure that looks like a real regression.

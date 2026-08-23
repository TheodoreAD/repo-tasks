# Test tiers

Three tiers, with deliberately different prerequisites. The default one must stay runnable anywhere.

| tier        | command                        | needs                                                | runs on every commit? |
| ----------- | ------------------------------ | ---------------------------------------------------- | --------------------- |
| unit        | `inv quality.test`             | nothing beyond the dev dependency group              | yes                   |
| integration | `inv quality.test-integration` | Docker daemon, `devpi-server`, `--group integration` | no — opt-in           |
| clean-OS    | part of the integration tier   | Docker daemon                                        | no — opt-in           |

## Why the split is enforced structurally

`quality.test`/`check`/`precommit` must never start silently requiring Docker. Enforced by
`pytest.ini`'s `addopts` carrying `--ignore=tests/integration`, with `quality.test_integration`
overriding it (`-o addopts=...`) for its own invocation only. Directory-level exclusion was enough —
no pytest marker needed.

Each integration fixture **skips gracefully** (`pytest.skip`, never a hard failure) when its
prerequisite is missing — `shutil.which("devpi-server")`, a Docker-daemon reachability check. A
missing prerequisite must never look like a real regression.

`test_integration` is deliberately _not_ in `check`/`precommit`'s `pre=[...]`.

## Unit tier: mocked `c.run`

Every task module has a `tests/test_<module>.py` following `tests/test_quality.py`'s
`MockContext`/`Result` pattern, asserting exact command-string construction. This is the whole tier
— fast, hermetic, no external anything.

Its blind spot is real and worth stating: mocked fixtures only exercise the payloads someone thought
to write. Two genuine `dist.py` parsing bugs survived full unit coverage and were caught immediately
by the integration tier the first time it ran against a real index (see below).

## Integration tier: real services, locally

### Package index: `devpi-server`, not `pypiserver`

`pypiserver` (MIT/zlib, actively maintained) was the more obvious first pick, but its `CHANGES.rst`
confirms it **has never added PEP 691 JSON Simple API support** — only the PEP 503 HTML index.
Testing `dist.versions()` against it would exercise only the HTML-fallback branch, leaving the JSON
branch — the primary path against any modern index, including real PyPI — completely untested.

`devpi-server` (MIT, actively maintained) serves both: PEP 691 JSON on its own `/simple` endpoint
and PEP 503 HTML for non-JSON-aware clients. It is the one local server that exercises both of
`dist.py`'s branches against something real.

`simple-repository-server` was also considered and not used: it does PEP 691 only via a
`?format=...` querystring rather than real `Accept`-header content negotiation, so it wouldn't
exercise `dist.py`'s actual `_get(url, accept=...)` path.

No pytest fixture plugin is depended on. `pytest-devpi-server` exists in the
`man-group/pytest-plugins` monorepo, but that repo's maintenance freshness wasn't confirmed — verify
before ever reaching for it. The hand-rolled fixture runs `devpi-init`, launches `devpi-server` as a
subprocess on a scratch server-dir and free port, polls until up, creates the index, yields the
URLs, and terminates on teardown.

[PITFALL: devpi's PEP 691/503 simple endpoint lives at `<index-url>/+simple/<name>/`, **not** the
bare index URL. The bare `<index-url>/<name>/` is a different HTML-only project-detail page that
404s/415s on the JSON accept header. The upload target (`uv publish --publish-url`) is the bare
index URL, with no `+simple` or `/legacy/` suffix — the two URLs are not interchangeable.]

[PITFALL: `devpi use` without `--set-cfg` only _reports_ what it would touch in the active venv's
pip/uv config — it never writes it. The fixture relies on that and points `--clientdir` at its own
scratch dir, so it can never disturb the developer's real config. Never add `--set-cfg`.]

Server-side setup sequence, each call with `--clientdir <dir>`:
`devpi-init --serverdir <dir>
--root-passwd <pw>` (non-interactive, avoiding the deprecated
interactive `--passwd` prompt), then `devpi use http://127.0.0.1:<port>`,
`devpi login root --password <pw>`, `devpi index -c test
bases=root/pypi`. The `devpi`
upload/install subcommands are never used — `dist.py`'s own `uv build`/`uv publish` do the real work
being tested.

### Docker registry: `registry:3` via `testcontainers`

`registry:3` is Docker's own [Distribution](https://github.com/distribution/distribution) registry
(Apache-2.0) — the same engine behind Docker Hub, GHCR, GitLab Registry, and Harbor. It runs
open/insecure by default with no auth or TLS, which Docker's own deploy docs call "only appropriate
for testing." That is exactly this use case.

`testcontainers` provides the fixture shape rather than hand-rolling against the `docker` SDK: its
`ryuk`-based auto-cleanup means no leaked containers even on a crashed run, which is real
boilerplate (port allocation, readiness polling, teardown-on-failure) a hand-rolled fixture would
reimplement.

[PITFALL: push and pull against `127.0.0.1:{port}/...` explicitly, never `localhost`. Docker's
`127.0.0.0/8` auto-insecure-registry exemption reliably covers the literal `127.0.0.1`, but Docker's
own docs warn against relying on it long-term, and it is not guaranteed to extend to the `localhost`
hostname identically on every platform — Docker Desktop on macOS/Windows can differ from Linux
`dockerd`. A machine that doesn't get the automatic exemption needs
`{"insecure-registries": ["127.0.0.1:<port>"]}` in `daemon.json`.]

### What this tier caught

Two real `dist.py` bugs, immediately, on first run — neither reachable through the mocked unit
fixtures, whose JSON/HTML payloads happened not to hit either gap:

- devpi's JSON file entries omit the (PEP 691-optional) `"version"` key entirely.
- devpi's HTML hrefs carry a `#sha256=...` fragment that broke `_html_versions`' regex.

Both fixed, with unit-level regressions pinning them:
`test_versions_derives_from_json_filename_when_version_key_absent` and
`test_versions_html_fallback_strips_sha256_fragment` in `tests/test_dist.py`.

## Clean-OS tier: testing user-wide effects

Several tasks mutate a real `$HOME`, not just the consumer repo — `selfinstall.py`
(`uv tool
install`), `agents.py` (writes `~/.claude/settings.json`, `~/.cache/claude-code/*`),
`direnv.py` (`direnv allow`), and the `configs.py`/`configure.py` distribution machinery. Testing
those against the dev machine's real `$HOME` risks clobbering real files and isn't reproducible in
CI.

`tests/integration/clean-os.Dockerfile` is a deliberately minimal `debian:bookworm-slim` plus
`ca-certificates`/`curl`/`git`/`direnv`, with one **non-root** `tester` user and `uv` installed
under that user's own `~/.local/bin`. Non-root is the point: these tasks are all meant to stay
user-scoped, and running as root would silently let one get away with writing somewhere a real user
never could.

It lives under `tests/integration/`, deliberately not at the repo root —
`projects.discover_docker_images(c)` treats a root-level `Dockerfile` as the repo's own implicit
shippable image, and this one is test infrastructure.

The fixture builds and pushes it through `repo_tasks.docker`'s own real `build`/`push`/`release`
tasks rather than hand-rolled build code, which dogfoods those tasks against a real Dockerfile —
until then they had only ever run against a synthetic `FROM scratch` image or mocked `c.run`.

[PITFALL: docker-py's `images.build()` eagerly resolves credentials for **every** registry listed in
`~/.docker/config.json` before building anything, so a single stale entry fails a build that never
touches that registry. Found live: a stale `gcr.io` → `docker-credential-gcloud` entry tied to a
deleted account failed the whole build. `docker.py`'s tasks always shell out to the plain `docker`
CLI, never the Python SDK, so they are immune — a corollary of dogfooding them, not a workaround.]

## Adding a tier or a fixture

The bar this repo applies, following the `db-defaults` skill's philosophy: permissively licensed,
actively maintained, low-boilerplate, and testable inside a plain `pytest` run with no cloud
account. The one deliberate departure from that skill's usual "no Docker" criterion is here — when
the subject under test _is_ Docker, a local daemon is unavoidable. That is still "local," just not
"no Docker."

Check whether a candidate actually exercises the code paths you care about before adopting it. The
`pypiserver`/`devpi-server` decision turned entirely on that question and would have gone the other
way on maintenance and popularity alone.

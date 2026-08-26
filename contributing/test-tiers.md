# Test tiers

Three tiers, with deliberately different prerequisites. The default one must stay runnable anywhere.

| tier        | command                      | needs                                   | runs on every commit? |
| ----------- | ---------------------------- | --------------------------------------- | --------------------- |
| unit        | `inv test.unit`              | nothing beyond the dev dependency group | yes                   |
| integration | `inv test.integration`       | Docker daemon                           | no — opt-in           |
| clean-OS    | part of the integration tier | Docker daemon                           | no — opt-in           |

`inv test.all` runs the unit tier then the whole integration tier. `inv test.smoke` and
`inv test.regression` slice the integration tier by the `smoke` marker — the fast happy-path set
versus everything else — and are registered before anything is marked, since `--strict-markers`
rejects an unregistered marker.

`inv test.workflows` is not a tier: it runs the repo's own GitHub Actions workflows locally through
[act](https://github.com/nektos/act) (Docker containers standing in for the hosted runners), which
re-runs the gate the way CI would. That is only worth doing when a workflow file itself changed —
the static half, `inv quality.workflow-check` (actionlint + zizmor), is what runs on every commit.
`inv docker.check` sits on the same line for images: BuildKit's own checks need a daemon, so
`inv quality.dockerfile-check` (hadolint) is the half in the gate and `docker.check` is exercised
from the integration tier. act's runner-image map lives in `~/.config/act/actrc`, deployed by
`power-user-linux-setup`'s `[packages.act]`; without it act's first run is an interactive prompt,
fatal under a task.

## Why the split is enforced structurally

`test.unit`/`check`/`precommit` must never start silently requiring Docker. Enforced by
`pytest.ini`'s `testpaths = tests/unit`: the default run reaches the unit tier and nothing else,
because that is the only directory it names.

[DECISION: an include, not an exclude. This was `--ignore=tests/integration` in `addopts`, which is
the brittle shape — a _new_ directory under `tests/` joins the default run the moment somebody adds
one, and nobody remembers to update an exclude. With `testpaths`, a new tier is invisible until it
is named. Same rule of thumb as `plans/2026-08-19-gitignore-tool-alignment.md`.]

[PITFALL: `testpaths` must list `tests/unit` **alone**. Listing `tests/unit tests` looks like a
tidier fallback for a repo without the split, but measured, with both directories present it
collects the integration tier into the default run — exactly what this is meant to prevent.]

The fallback for a simple repo with a flat `tests/` comes from pytest itself, not from task code:
with `testpaths` naming a directory that does not exist, pytest warns
(`No files were found in testpaths ... Searching recursively from the current directory instead`)
and finds the tests anyway. That is why `test.unit` runs a bare `pytest` and names no path — naming
one would defeat it, since an explicit path that does not exist is a hard exit-4 usage error rather
than a warning. The other targets do name a path, so each checks the directory exists first and
prints-and-returns when it does not.

A flat `tests/` is a **supported layout, not a lesser one**. The split is what this repo and every
generated project get by default, because two tiers with different prerequisites is the shape that
needs enforcing; a project with one tier and no Docker is not doing anything wrong, and nothing in
the shipped config may punish it.

[PITFALL: `filterwarnings = error` broke exactly that, for a day, in every consumer. The fallback's
own notice is a `PytestConfigWarning`, so promoting warnings to errors turned the documented
graceful path into a hard exit-1 crash — a repo with a plain `tests/` could not run `pytest` at all.
The shipped `pytest.ini` now carries one narrow `ignore` for that single message, and
`tests/integration/test_written_files_integration.py` runs a real `pytest` subprocess over both
halves: a flat tree passes, and any _other_ warning still fails. A config that documents a fallback
must not promote that fallback's own notice.]

`test.integration` is deliberately _not_ in `check`/`precommit`'s `pre=[...]`; only `test.unit` is.

### The three promises, all three enforced

`test.unit`'s docstring promises "no Docker, no network, nothing outside tmp_path". Each of the
three is enforced by something, rather than by whoever writes the next test remembering:

| promise             | enforced by                                        |
| ------------------- | -------------------------------------------------- |
| no Docker           | `pytest.ini`'s `testpaths = tests/unit` (above)    |
| nothing outside tmp | the autouse `tmp_cwd` / `isolated_home` fixtures   |
| no network          | the autouse `no_network` fixture (`pytest-socket`) |

The network half was the one enforced by nothing until 2026-08-27. `no_network` calls
`disable_socket(allow_unix_socket=True)`, so any `socket.socket()` in a unit test raises
`SocketBlockedError` naming the call. Unix sockets stay allowed — local IPC is never the coupling
this guards against.

[DECISION: an autouse fixture, not `--disable-socket` in `pytest.ini`'s `addopts`. That file is
shipped to every consumer by `configs.pull` while `pytest-socket` sits in this repo's own `dev`
group and _not_ in the exported `repo-tasks-quality` manifest — a flag there would fail every
consumer's `pytest` at startup with an unrecognized argument. The fixture lives in test structure,
which this package does not ship; that is `scaffoldapy`'s half of the split. Seeding the same
fixture into generated repos is what would move the plugin into the manifest, and belongs to that
repo.]

[DECISION: verified compatible with the `db-defaults` skill's picks before adopting, since that
skill's whole point is real local backing services rather than mocks. Every default there is
in-process or file-backed — `sqlite3`, `sqlalchemy`, `duckdb`, `tinydb`, `diskcache`, FTS5, `huey`,
`apscheduler`, `blinker` — and opens no socket. `qdrant-client` is the one that can go either way,
and it splits exactly along the intended line: embedded mode (`path=`/`:memory:`) passes,
`QdrantClient(url=…)` is blocked. That is the guard enforcing the stated goal, not fighting it.]

## Conftest layout

Three files, which is most of the reason the directories are split at all:

- `tests/conftest.py` — what both tiers share: `repo_root`, and `sample_chart_dir`, which resolves
  the dogfood chart's location out of `repo-tasks.toml` rather than as a literal path. Both tiers
  read that chart, and a literal in either is a trap — moving the fixture tree leaves it pointing at
  nothing, surfacing as a confusing mid-test read error rather than at collection.
- `tests/unit/conftest.py` — `c` (the `MockContext` nearly every unit test wants) and `tmp_cwd` (an
  empty directory that is also the working directory). A test needing a _specific_ run result still
  builds its own `MockContext(run=Result(exited=...))`; that is the intended split, not an
  oversight, and about 30 tests legitimately do it.

  [PITFALL: `tmp_cwd` exists because most task modules resolve inputs relative to the working
  directory — `projects.py` reads `pyproject.toml` and `repo-tasks.toml`, `dist.clean` _removes_
  `dist/`, `selfinstall` reads its stamp file. A test that forgets `monkeypatch.chdir` reads, or
  deletes, this repo's own files. Taking the fixture makes that impossible to forget.]

  It also holds the two other autouse fixtures. `isolated_home` points `HOME` at a fresh temp
  directory for every unit test; `no_network` disables sockets (`pytest-socket`'s `disable_socket`,
  Unix sockets still allowed) so the tier's third promise is enforced rather than merely stated —
  see "The three promises" above. [PITFALL: `tmp_path` sandboxes the working tree, not the user.
  `agents.wire_claude_hook` writes an env-cache file under `Path.home()/.cache/claude-code`, and
  before the fixture existed each unit run left one stale `tmp-pytest-of-*` file per test in the
  developer's real cache — ~400 accumulated before anyone noticed, because nothing failed. The
  fixture is autouse for the same reason `tmp_cwd` exists, and `agents.py` resolves the cache
  directory at call time rather than as an import-time constant so the override actually lands.]
- `tests/integration/conftest.py` — the container and index fixtures, which no unit test should be
  able to reach by accident.

It is exemplary by being read, not distributed: this package ships tool config and the quality
dependency manifest, never project structure or tests. That is `scaffoldapy`'s half of the split.

The devpi fixture still **skips gracefully** (`pytest.skip`, never a hard failure) when
`devpi-server` isn't on PATH. That is now belt-and-braces rather than the main path — devpi lives in
`dev` like everything else, so a plain `inv venv.sync` installs it — but it keeps a half-synced
environment from looking like a real regression. A missing Docker daemon deliberately fails loudly
instead.

## Unit tier: mocked `c.run`

Every task module has a `tests/unit/test_<module>.py` following `tests/unit/test_quality.py`'s
`MockContext`/`Result` pattern, asserting exact command-string construction. This is the whole tier
— fast, hermetic, no external anything.

Its blind spot is real and worth stating: mocked fixtures only exercise the payloads someone thought
to write. Two genuine `dist.py` parsing bugs survived full unit coverage and were caught immediately
by the integration tier the first time it ran against a real index (see below).

That blind spot is exactly why the two coverage questions land on opposite sides of the gate.
`inv test.untested-modules` — does every module under `src/` have a `tests/unit/test_<module>.py`? —
is in `quality.check`: the question has a true answer regardless of how the tier is written. A
module with no code in it is skipped, which in practice means a docstring-only `__init__.py`; the
only test such a file could have is a placeholder. [PITFALL: the skip was missing at first and
`scaffoldapy`'s e2e tier is what found it — all ten rendered combinations failed the generated
repo's own gate, because the template's `__init__.py` is exactly one docstring. An `__init__.py`
that re-exports still needs its test: an `__all__` is a contract, and `repo_tasks/__init__.py`'s
collection wiring is one.] `inv test.coverage` is a standalone report with no `--cov-fail-under`,
because a line-coverage number over a tier of command-string assertions mostly measures how much
mocking got written, and the two `dist.py` bugs above are what a threshold on it would have called
covered.

## Integration tier: real services, locally

### Package index: `devpi-server`, not `pypiserver`

`pypiserver` (MIT/zlib, actively maintained) was the more obvious first pick, but its `CHANGES.rst`
confirms it **has never added PEP 691 JSON Simple API support** — only the PEP 503 HTML index.
Testing `dist.list-versions()` against it would exercise only the HTML-fallback branch, leaving the
JSON branch — the primary path against any modern index, including real PyPI — completely untested.

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
`test_versions_html_fallback_strips_sha256_fragment` in `tests/unit/test_dist.py`.

### The dogfood sample: `tests/fixtures/sample-service`

`tests/integration/test_dogfood_sample_service.py` runs `docker.release` against the real
multi-stage Dockerfile and `helm.lint`/`package`/`push` against the real chart, both landing in the
same `registry:3` container, then reads them back through the registry's own API. Its siblings prove
the tasks work _at all_ (a synthetic `FROM scratch` image); this proves they work on the artifacts a
consumer would actually write, including that the container really runs the wheel `dist.build`
produced and that the chart renders the exact tag `docker.release` pushed.

Only the image _ref_ is redirected at the local registry; Dockerfile, build context, chart path, and
version group all come from the committed `repo-tasks.toml`, so the test cannot pass against a
configuration nobody ships.

[PITFALL: `helm push` needs `--plain-http` against a TLS-less registry. Unlike docker, helm has no
automatic `127.0.0.0/8` insecure-registry exemption — it speaks HTTPS to a loopback registry like
any other and fails with `server gave HTTP response to HTTPS client`.]

### Real group bump: no Docker, no devpi

`tests/integration/test_version_integration.py` runs `bump-my-version` for real against a throwaway
git repo holding a `pyproject.toml` and a `Chart.yaml` read from the dogfood chart. It needs neither
of this tier's services — `bump-my-version` is a runtime dependency, so the module never skips — and
lives here only because it shells out for real (git commits, git tags, a subprocess), which is
exactly what the unit tier promises not to do.

It closed a standing [UNVERIFIED]: `tests/unit/test_version.py` pins the _generated config_, but
whether bump-my-version actually finds those search strings in a real `Chart.yaml` had never been
executed.

This module used to be uncollectable in practice: `tests/integration/conftest.py` imports
`testcontainers` at module scope, and `testcontainers` lived in a separate opt-in dependency group,
so the whole directory failed to import without it — including this module, which needs nothing from
it. Folding every group into `dev` removed the cause rather than working around it.

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

### What the tier covers

`tests/integration/test_clean_os_integration.py` smoke-tests the fixture itself (non-root, clean
`$HOME`, source copied in). `tests/integration/test_clean_os_user_effects.py` holds the real
mutating tests — what only this tier can cover, since the unit tests already exercise the pure
filesystem/JSON logic against `tmp_path`:

- `selfinstall.py`'s real install command produces a working global `inv` under the non-root user's
  own `~/.local/bin` on a machine with no Python at all — the `--with-executables-from invoke` claim
  its module docstring calls load-bearing — pointed at the container's local source copy instead of
  the GitHub URL, so no dependency on the real remote's tags or network.
- That installed `inv` resolves a consumer repo's `from repo_tasks import ns` tasks.py with no
  project venv existing yet — the daily-driver model, end to end.
- `direnv.allow` flips a really-blocked `.envrc` to allowed, proven behaviorally via `direnv export`
  failing before and succeeding after.
- `agents.wire-claude-hook` wires a fresh project on a fresh `$HOME`, including the env cache file
  materializing under the real `~/.cache/claude-code`.

### Fixture scope: one container per module, disjoint mutations within one

`clean_os_container` is module-scoped, which means one fresh container _per test module_ — the
smoke-test module can never observe the mutating module's writes. Within the mutating module, tests
deliberately share the container under one rule: every mutation lands on a disjoint path (the tool
install under `~/.local`, direnv's allow database, a scratch project dir plus
`~/.cache/claude-code`), and shared prerequisites (the tool install) are fixtures, never test
file-order. A future test that can't keep the disjoint-paths property gets a function-scoped
container of its own instead of joining that module — the isolation cost is paid only when a test
actually needs it, since a per-test container would repeat the `uv tool install` (a real Python +
dependency download) for every test.

## Adding a tier or a fixture

The bar this repo applies, following the `db-defaults` skill's philosophy: permissively licensed,
actively maintained, low-boilerplate, and testable inside a plain `pytest` run with no cloud
account. The one deliberate departure from that skill's usual "no Docker" criterion is here — when
the subject under test _is_ Docker, a local daemon is unavoidable. That is still "local," just not
"no Docker."

Check whether a candidate actually exercises the code paths you care about before adopting it. The
`pypiserver`/`devpi-server` decision turned entirely on that question and would have gone the other
way on maintenance and popularity alone.

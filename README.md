# repo-tasks

Shared, reproducible [invoke](https://www.pyinvoke.org/) tasks for personal Python repos — one
module per facility: `quality` (`lint`/`format`/`type_check`/`shell_check`/`shell_format`/
`workflow_check`/`dockerfile_check`, and the composite `fix`/`check`/`precommit` graph), `test` (one
target per tier — `unit`/`integration`/`smoke`/`regression`/`all`, with only the unit tier in the
default gate, plus `untested-modules` and the standalone `coverage` report — plus `workflows`, which
runs the repo's GitHub Actions locally through [act](https://github.com/nektos/act)), `venv`
(`sync`/`create`/`delete`/`install_wheel` — lock-respecting venv lifecycle, CI/docker-aware), `deps`
(`lock`/`check`/`list`/`tree`/`export` — the only tasks that ever write `uv.lock`), `dist`
(`clean`/`build`/`publish`/`versions` — build a wheel, publish it, and query a package index for a
project's released versions), `docker` (`check`/`build`/`push`/`release` — image name/Dockerfile
resolved from `repo-tasks.toml` or a zero-config root `Dockerfile`, tagged from the version-grouping
model), `helm` (`lint`/`package`/`push` — charts resolved from `repo-tasks.toml`'s `[[helm]]`
entries, versioned by that same grouping model), `direnv` (`allow` — idempotent shell
auto-activation), `agents` (`claude_hook` — wiring an AI coding agent's shell execution to pick up
the direnv environment), `dev_env` (`setup` — the one-time post-clone bootstrap composing all of the
above), and `docs` (`clean`/`build`/`serve`, wrapping [zensical](https://zensical.org/)), `configs`
(`pull`/`diff` — materializes
`ruff.toml`/`pyrightconfig.json`/`dprint.json`/`pytest.ini`/`zizmor.yml`/ `.editorconfig` from this
package's own canonical copies), and `repo_tasks` (nested as `repo-tasks.*` on the CLI —
`update`/`status`/`version`/`stamp`, managing this package's own daily-driver global install,
decoupled from any consumer's dependency groups) — extracted from
[power-user-linux-setup](https://github.com/TheodoreAD/power-user-linux-setup)'s own `tasks/`
directory so a fix or improvement lands once and reaches every consumer deliberately (a pinned
dependency bump), instead of being hand-copied and silently drifting per repo. `inv configure`
(bare, unnested) is the one command anything outside this package should ever need to name directly
— `venv`/`direnv`/`agents`/`configs` are free to be reshuffled later without anything downstream (a
[`scaffoldapy`](https://github.com/TheodoreAD/scaffoldapy) `_tasks` hook, a human) noticing.

## Scope

This is the "anything a repo in this family does _repeatedly_, identically, forever" piece — quality
tooling, venv/dependency lifecycle, canonical tool config, the dev-loop bootstrap. What's generated
once and then hand-maintained per repo (project structure, `AGENTS.md`, `pyproject.toml`) is
[`scaffoldapy`](https://github.com/TheodoreAD/scaffoldapy)'s job instead, not this package's. See
[`contributing/repo-family-architecture.md`](https://github.com/TheodoreAD/power-user-linux-setup/blob/master/contributing/repo-family-architecture.md)
in `power-user-linux-setup` for the full three-repo split and the decision rule behind it. The
reasoning behind this repo's own design — decisions, rejected alternatives, pitfalls — is indexed in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

## Design

No per-repo allowances: every consumer uses the identical `fix`/`check`/`precommit` composite,
unmodified. `precommit` (`fix` then `check`) is the one command an agent always runs — no need to
know or invoke the individual tools. Every task, leaf and composite alike, carries a succinct
one-line docstring — what `inv -l` shows as help text. Every command echoes (`echo=True`) what it
ran, except a step that would involve a secret (none here do). `shell_check`/`shell_format_*` no-op
cleanly on a repo with zero `*.sh` files, `workflow_check` (actionlint + zizmor) on one with no
`.github/workflows`, and `dockerfile_check` (hadolint) on one with no Dockerfiles, so they're safe
to run unconditionally — no per-repo opt-out needed.

Each tool gets its own dedicated config file (`ruff.toml`, `pyrightconfig.json`, `pytest.ini`) — not
consolidated into `pyproject.toml` — so a template-driven config update across many repos can
diff/replace one file cleanly instead of risking a monolithic block.

## Installing

**Recommended: the global daily-driver tool.** One install serves every repo in the family,
decoupled from any single repo's own dependency groups — the point of the runtime/dev-venv split
(see `power-user-linux-setup`'s
[`plans/2026-08-20-runtime-dev-venv-split.md`](https://github.com/TheodoreAD/power-user-linux-setup/blob/master/plans/2026-08-20-runtime-dev-venv-split.md)):

```shell
uv tool install --with-executables-from invoke 'repo-tasks @ git+https://github.com/TheodoreAD/repo-tasks'
```

`--with-executables-from invoke` is required, not optional — confirmed hands-on that
`uv tool
install` does not expose a dependency's own console scripts by default (the same limitation
pipx historically had, `--include-deps` was the required opt-in there). Without this flag you'd get
`repo-tasks` installed but no `inv`/`invoke` binary on `PATH` at all. This one install puts
`inv`/`invoke` on `PATH` globally; every consumer repo's own `tasks.py`
(`from repo_tasks import
ns`) then resolves `repo_tasks` from this same install — no per-repo
dependency needed at all. `inv repo-tasks.update` moves this install forward later (to the latest
tagged release); `inv repo-tasks.status`/`.version` inspect what's currently active.

**Alternative: a pinned per-repo dev dependency**, for a repo that wants its own locked version
independent of the shared global install:

```shell
uv add --dev git+https://github.com/TheodoreAD/repo-tasks
```

Git-as-artifact-store, no PyPI either way. Under this pinned path, `uv.lock` freezes an exact commit
— a later fix reaches that consumer only via a deliberate `uv lock --upgrade-package
repo-tasks` (or
a pinned `@<tag>` bump) plus a committed lockfile change, not automatically.

## Using

```python
# consumer repo's tasks.py, at the repo root
from repo_tasks import ns
```

That's the entire file — no local override, no `add_collection` boilerplate. `ns` is a ready-made
root `Collection` with every task module this package ships already nested under its own name, so
`inv quality.precommit` is the one command, identical across every consumer repo, and stays that way
automatically as new modules (`helm`, ...) land here — nothing to change on the consumer side when
they do. Every leaf task (`lint_check`, `type_check`, `test`, ...) is also individually invocable
(`inv quality.lint-check`, `inv test.unit`, etc.) — each has its own docstring, so `inv -l` alone is
enough to know what's available.

Each module is also importable on its own (`from repo_tasks import quality`) for a consumer that
wants to hand-pick a subset rather than take the full `ns` — see `src/repo_tasks/__init__.py` for
the exact wiring `ns` does, to replicate a narrower version of it.

Every consumer repo needs its own `pyrightconfig.json` — `check` runs `type_check` unconditionally
(no allowances), so type-check config must exist everywhere `check` runs.

`inv dev-env.setup` is the one command to run once after cloning: `venv.create` (syncs `.venv` from
`uv.lock`) + `direnv.allow` + `agents.wire-claude-hook` (wiring Claude Code's Bash tool to
auto-activate the venv too, no-ops if the repo has no `.envrc`) — `dev_env.py` itself owns no logic,
it's pure orchestration of those three modules. `inv docs.build`/`docs.serve` assume `zensical` is
installed — add it as a project `docs` dependency group, it isn't a dependency of this package.

### venv/deps: lock-respecting, CI/docker-aware

`venv.sync` (and `venv.create`, its no-args first-time wrapper) always run `uv sync --locked` — this
fails loudly on a missing or stale `uv.lock` instead of uv's own default of silently rewriting it.
`inv deps.lock` is the _only_ task in this package that ever runs `uv lock`; every other
`deps.*`/`venv.*` task is read-only with respect to the lockfile. The one other write to it is
`version.bump` moving the project's own embedded version (uv's `--locked` rejects a lock whose copy
disagrees with `pyproject.toml`), in the same commit as the bump, verified by `uv lock --check`
before that commit lands — see
[`contributing/versioning.md`](contributing/versioning.md#uvlock-moves-with-the-bump).

One `uv lock` failure a plain re-run never fixes: a workspace member whose directory _moved_.
`uv.lock` still records the old editable path, and both `deps.lock` and `deps.check` fail with
`Distribution not found at: <old path>` until `inv deps.lock --package <member>` re-resolves it —
`deps.lock` recognises that message and prints exactly that command. Renaming a member in place or
removing it needs nothing special.

Two independent flags cover CI/docker, instead of one opaque `ci=` boolean — a CI test job usually
still wants dev deps, while a runtime image wants neither:

```shell
inv venv.sync --no-editable            # CI test job: real (non-editable) install, keep dev deps
inv venv.sync --no-editable --no-dev   # runtime image: neither dev deps nor an editable install
inv venv.sync --no-install-project     # deps-only venv, for a Docker/CI layer cache keyed on
                                        # just pyproject.toml + uv.lock, before any repo code lands
```

A wheel-based prod image builds on top of that deps-only layer: `inv dist.build` to produce
`dist/*.whl`, then `inv venv.install-wheel` (`uv pip install --no-deps`) to add just the project
package to the same `.venv` — no re-resolution, so the shipped container runs exactly the wheel that
could also go straight to `inv dist.publish`. `tests/fixtures/sample-service/Dockerfile` is that
recipe written out in full, against a real service.

### dist: build, publish, and query a package index

`inv dist.build` builds a wheel (`--sdist` for the sdist+wheel pair PyPI conventionally expects)
into a freshly-cleaned `dist/` — a stale wheel from a previous version can never survive into a
fresh build. `inv dist.publish` always builds fresh first (`pre=[build]`) and runs `uv publish`
(`--index`/`--dry-run` passed through). `inv dist.list-versions` lists a project's published
versions by querying a package index directly — PEP 691 JSON Simple API, falling back to the PEP 503
HTML file listing if the index doesn't serve the JSON media type — since `uv` itself has no
list-remote-versions subcommand. `dist.py` never touches `.venv` or installs anything editable; it's
orthogonal to `venv.py`/`deps.py` by construction. All three take `--project` to name a workspace
member; omitted, they act on the repo's own root project.

### docker: build, push, and release an image

`inv docker.build` builds a docker image (`docker build`, or
`docker buildx build --platform
... --push` when `--platforms` is given — buildx can't `--load` a
multi-platform result locally, so that path pushes as part of `build` itself). `inv docker.push`
pushes the single-arch path. `inv docker.release` builds and pushes an image tagged with its version
group's current version, plus `latest`. Image name/Dockerfile/path always come from
`projects.discover_docker_images(c)` — `repo-tasks.toml`'s `[[docker]]` entries if present, or a
zero-config default: a `Dockerfile` at the repo root becomes one implicit image, named after the
repo's python project (so its version group resolves for free) or the repo directory if there isn't
one. `--project` selects among multiple discovered images; omit it for the common single-image case.

### helm: lint, package, and push a chart

`inv helm.lint` runs `helm lint` against a chart; `inv helm.package` packages it into `dist/helm/`;
`inv helm.push` pushes the packaged `.tgz` to an OCI registry (`helm push`). Chart path, registry,
and version group always come from `projects.discover_helm_charts(c)` — `repo-tasks.toml`'s
`[[helm]]` entries, with no zero-config fallback (unlike docker, a chart has no single canonical
root location, and a pushable chart needs a registry only explicit config can supply); every task
no-ops cleanly in a repo with no entries. The chart's `version`/`appVersion` are written by
`version.py` as part of its group's bump — a chart sharing a `group` with the docker image it wraps
releases in lockstep with it (see [`contributing/versioning.md`](contributing/versioning.md)) — and
the `.tgz` a push targets is named from that group version, so a chart that was never packaged (or
drifted from its group's version) fails loudly instead of pushing the wrong thing. `--project`
selects among multiple discovered charts; omit it for the common single-chart case. `--plain-http`
is there for a registry serving no TLS (a local dev registry): helm has no equivalent of docker's
automatic loopback insecure-registry exemption, so it must be asked for explicitly.

### monorepos: workspace members, version groups, and the sample service

A repo with several projects declares them the way `uv` already does — `[tool.uv.workspace]`'s
`members`/`exclude` globs in the root `pyproject.toml`, no parallel manifest.
`projects.discover_python_projects(c)` resolves the root project first, then each member, and that
ordering is what "the repo's own project" means to every task's no-flag invocation. A single-project
repo needs no workspace table at all and behaves exactly as before.

Docker images and Helm charts aren't modelled by `uv`, so they live in `repo-tasks.toml` instead
(`[[docker]]`/`[[helm]]`). An entry's `group` is what ties artifacts into one release unit: a
service's image, the chart that deploys it, and the python project they're built from share one
`group`, so `inv version.bump --group <name>` moves all three in one commit and one tag. See
[`contributing/versioning.md`](contributing/versioning.md) for what may share a group and why.

One version, spelled per artifact: `pyproject.toml` holds PEP 440 (`1.1.0rc2`), `Chart.yaml` and the
docker tag hold SemVer (`1.1.0-rc.2`), and nothing converts one string into another — the parts are
the source of truth. `inv version.bump --part major|minor|patch` lands on `rc1` (`--no-rc` goes
straight to the final), `--part rc` cuts the next candidate, `--part final` drops it; the gitflow
tasks drive that cycle on the release branch (`inv gitflow.release-candidate` tags and pushes a
candidate for staging). A dev build — `inv dist.build --dev`, `inv docker.build --dev`,
`inv helm.package --dev` — rewrites the working tree's version from git (`1.0.1.dev3+g1a2b3c` /
`1.0.1-dev.3.g1a2b3c`) without committing, refuses a dirty tree, and never receives `latest` or a
PyPI upload.

`tests/fixtures/sample-service/` is this repo's own worked example of all of it — a stdlib-only HTTP
service that is simultaneously a workspace member, the `[[docker]]` image built by a multi-stage
Dockerfile following the venv/deps recipe above, and the `[[helm]]` chart that deploys it, all under
`group = "sample-service"`. It exists to be exercised, not imitated wholesale: the integration tier
builds, pushes, and reads it back on every run of `inv test.integration`.

### repo-tasks: managing the global daily-driver install

`inv repo-tasks.version` prints the currently-active `repo-tasks` version (whatever `inv` process is
running — normally the global daily-driver install from the "Installing" section above).
`inv repo-tasks.update` moves that global install forward to the latest tagged release (falls back
to the default branch with a printed warning if nothing's been tagged yet — true of this repo itself
pre-first-release). There's deliberately no version pinning for this day-to-day path: updates are
manual either way, and reproducibility is handled separately, below.

`inv configure` stamps a `bootstrap-repo-tasks.sh` at the repo root, pinning whichever `repo-tasks`
version was active when `configure` last ran. **This script is for CI and reproducibility
archaeology only — never run it as a human on your own machine.** Running it would silently
reinstall the _global_ tool to whatever version _this_ repo happens to be pinned to, yanking it out
from under any other repo you're working on. A human always runs `inv repo-tasks.update` instead; CI
runs the committed, version-pinned script (before `inv` exists), then bare `inv <task>` after.
`inv repo-tasks.status` compares the two — the globally-installed version against what this repo's
stamped script currently expects — as a quick drift check.

## Developing

```shell
./bootstrap.sh          # uv sync + inv venv.create -- the one place a raw uv call is needed
inv dev-env.setup       # direnv + Claude Code hook, on top of the venv bootstrap.sh just built
inv quality.precommit
```

`./bootstrap.sh` is also exactly what CI runs (`.github/workflows/ci.yml`) before its own bare
`inv quality.check` — same commands as local dev, no separate CI-only recipe. This repo dogfoods its
own tasks against itself (`tasks.py` is `from repo_tasks import ns` — the same one-liner a consumer
uses).

Tests live in their own `test` namespace, one target per tier: `inv test.unit` (the only one in
`check`/`precommit` — no Docker, no network), `inv test.integration`, `inv test.smoke` and
`inv test.regression` (the `smoke` marker and its inverse), and `inv test.all`. A plain `pytest`
runs the unit tier alone, because `pytest.ini`'s `testpaths` names `tests/unit` and nothing else; in
a simpler repo with a flat `tests/`, pytest's own testpaths warning falls back to searching from the
working directory, so `test.unit` works there unchanged.

`inv test.integration` exercises `dist.py`/`docker.py`/`helm.py`/`version.py` — including the whole
`tests/fixtures/sample-service` round trip — against a real local `devpi-server` and a real local
`registry:3` container. It needs a reachable Docker daemon and is never part of `check`/`precommit`.
No extra dependency group to install: everything that isn't a main dependency lives in `dev`. A
missing `devpi-server` skips that half of the tier; a missing or unreachable Docker daemon fails it
outright rather than skipping. Every integration target no-ops cleanly in a repo with no
`tests/integration` directory.

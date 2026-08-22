# repo-tasks

Shared, reproducible [invoke](https://www.pyinvoke.org/) tasks for personal Python repos — one
module per facility: `quality` (`lint`/`format`/`type_check`/`shell_check`/`test`, and the composite
`fix`/`check`/`precommit` graph), `venv` (`sync`/`create`/`delete`/`install_wheel` — lock-respecting
venv lifecycle, CI/docker-aware), `deps` (`lock`/`check`/`list`/`tree`/`export` — the only tasks
that ever write `uv.lock`), `dist` (`clean`/`build`/`publish`/`versions` — build a wheel, publish
it, and query a package index for a project's released versions), `docker` (`build`/`push`/`release`
— image name/Dockerfile resolved from `repo-tasks.toml` or a zero-config root `Dockerfile`, tagged
from the version-grouping model), `direnv` (`allow` — idempotent shell auto-activation), `agents`
(`claude_hook` — wiring an AI coding agent's shell execution to pick up the direnv environment),
`dev_env` (`setup` — the one-time post-clone bootstrap composing all of the above), and `docs`
(`clean`/`build`/`serve`, wrapping [zensical](https://zensical.org/)), `configs` (`pull`/`diff` —
materializes `ruff.toml`/`pyrightconfig.json`/`dprint.json`/`pytest.ini`/ `.editorconfig` from this
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
in `power-user-linux-setup` for the full three-repo split and the decision rule behind it.

## Design

No per-repo allowances: every consumer uses the identical `fix`/`check`/`precommit` composite,
unmodified. `precommit` (`fix` then `check`) is the one command an agent always runs — no need to
know or invoke the individual tools. Every task, leaf and composite alike, carries a succinct
one-line docstring — what `inv -l` shows as help text. Every command echoes (`echo=True`) what it
ran, except a step that would involve a secret (none here do). `shell_check`/`shell_format_*` no-op
cleanly on a repo with zero `*.sh` files, so they're safe to run unconditionally — no per-repo
opt-out needed.

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
(`inv quality.test`, etc.) — each has its own docstring, so `inv -l` alone is enough to know what's
available.

Each module is also importable on its own (`from repo_tasks import quality`) for a consumer that
wants to hand-pick a subset rather than take the full `ns` — see `src/repo_tasks/__init__.py` for
the exact wiring `ns` does, to replicate a narrower version of it.

Every consumer repo needs its own `pyrightconfig.json` — `check` runs `type_check` unconditionally
(no allowances), so type-check config must exist everywhere `check` runs.

`inv dev-env.setup` is the one command to run once after cloning: `venv.create` (syncs `.venv` from
`uv.lock`) + `direnv.allow` + `agents.claude-hook` (wiring Claude Code's Bash tool to auto-activate
the venv too, no-ops if the repo has no `.envrc`) — `dev_env.py` itself owns no logic, it's pure
orchestration of those three modules. `inv docs.build`/`docs.serve` assume `zensical` is installed —
add it as a project `docs` dependency group, it isn't a dependency of this package.

### venv/deps: lock-respecting, CI/docker-aware

`venv.sync` (and `venv.create`, its no-args first-time wrapper) always run `uv sync --locked` — this
fails loudly on a missing or stale `uv.lock` instead of uv's own default of silently rewriting it.
`inv deps.lock` is the _only_ task in this package that ever runs `uv lock`; every other
`deps.*`/`venv.*` task is read-only with respect to the lockfile.

Two independent flags cover CI/docker, instead of one opaque `ci=` boolean — a CI test job usually
still wants dev deps, while a runtime image wants neither:

```shell
inv venv.sync --no-editable            # CI test job: real (non-editable) install, keep dev deps
inv venv.sync --no-editable --no-dev   # runtime image: neither dev deps nor an editable install
inv venv.sync --no-install-project     # deps-only venv, for a Docker/CI layer cache keyed on
                                        # just pyproject.toml + uv.lock, before any repo code lands
```

A wheel-based prod image builds on top of that deps-only layer: `inv dist.build` to produce
`dist/*.whl`, then `inv venv.install_wheel` (`uv pip install --no-deps`) to add just the project
package to the same `.venv` — no re-resolution, so the shipped container runs exactly the wheel that
could also go straight to `inv dist.publish`.

### dist: build, publish, and query a package index

`inv dist.build` builds a wheel (`--sdist` for the sdist+wheel pair PyPI conventionally expects)
into a freshly-cleaned `dist/` — a stale wheel from a previous version can never survive into a
fresh build. `inv dist.publish` always builds fresh first (`pre=[build]`) and runs `uv publish`
(`--index`/`--dry-run` passed through). `inv dist.versions` lists a project's published versions by
querying a package index directly — PEP 691 JSON Simple API, falling back to the PEP 503 HTML file
listing if the index doesn't serve the JSON media type — since `uv` itself has no
list-remote-versions subcommand. `dist.py` never touches `.venv` or installs anything editable; it's
orthogonal to `venv.py`/`deps.py` by construction.

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

`inv quality.test_integration` runs an opt-in real-service tier (`tests/integration/`) exercising
`dist.py`/`docker.py` against a real local `devpi-server` and a real local `registry:3` container —
never part of `check`/`precommit`, and not collected by a plain `inv quality.test` either
(`pytest.ini`'s `--ignore=tests/integration`). Needs `uv sync --group integration` (adds
`devpi-server`/`devpi-client`/`testcontainers`) and a reachable Docker daemon; a missing
`devpi-server` skips that half of the tier, a missing/unreachable Docker daemon fails it outright
rather than skipping.

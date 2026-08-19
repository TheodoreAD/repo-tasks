# repo-tasks

Shared, reproducible [invoke](https://www.pyinvoke.org/) tasks for personal Python repos — one
module per facility: `quality` (`lint`/`format`/`type_check`/`shell_check`/`test`, and the
composite `fix`/`check`/`precommit` graph), `venv` (`sync`/`create`/`delete`/`install_wheel` —
lock-respecting venv lifecycle, CI/docker-aware), `deps` (`lock`/`check`/`list`/`tree`/`export` —
the only tasks that ever write `uv.lock`), `direnv` (`allow` — idempotent shell auto-activation),
`agents` (`claude_hook` — wiring an AI coding agent's shell execution to pick up the direnv
environment), `dev_env` (`setup` — the one-time post-clone bootstrap composing all of the above),
and `docs` (`clean`/`build`/`serve`, wrapping [zensical](https://zensical.org/)) — extracted from
[power-user-linux-setup](https://github.com/TheodoreAD/power-user-linux-setup)'s own `tasks/`
directory so a fix or improvement lands once and reaches every consumer deliberately (a pinned
dependency bump), instead of being hand-copied and silently drifting per repo.

## Design

No per-repo allowances: every consumer uses the identical `fix`/`check`/`precommit` composite,
unmodified. `precommit` (`fix` then `check`) is the one command an agent always runs — no need to
know or invoke the individual tools. Every task, leaf and composite alike, carries a succinct
one-line docstring — what `inv -l` shows as help text. Every command echoes (`echo=True`) what it
ran, except a step that would involve a secret (none here do). `shell_check`/`shell_format_*`
no-op cleanly on a repo with zero `*.sh` files, so they're safe to run unconditionally — no
per-repo opt-out needed.

Each tool gets its own dedicated config file (`ruff.toml`, `pyrightconfig.json`, `pytest.ini`) —
not consolidated into `pyproject.toml` — so a template-driven config update across many repos can
diff/replace one file cleanly instead of risking a monolithic block.

## Installing

```shell
uv add --dev git+https://github.com/TheodoreAD/repo-tasks
```

Git-as-artifact-store, no PyPI. `uv.lock` freezes an exact commit — a later fix reaches a consumer
only via a deliberate `uv lock --upgrade-package repo-tasks` (or a pinned `@<tag>` bump) plus a
committed lockfile change, not automatically.

## Using

```python
# consumer repo's tasks.py, at the repo root
from repo_tasks import ns
```

That's the entire file — no local override, no `add_collection` boilerplate. `ns` is a ready-made
root `Collection` with every task module this package ships already nested under its own name, so
`inv quality.precommit` is the one command, identical across every consumer repo, and stays that way
automatically as new modules (`docker`, `python_pkg`, `helm`, ...) land here — nothing to change on
the consumer side when they do. Every leaf task (`lint_check`, `type_check`, `test`, ...) is also
individually invocable (`inv quality.test`, etc.) — each has its own docstring, so `inv -l` alone is
enough to know what's available.

Each module is also importable on its own (`from repo_tasks import quality`) for a consumer that
wants to hand-pick a subset rather than take the full `ns` — see `src/repo_tasks/__init__.py` for
the exact wiring `ns` does, to replicate a narrower version of it.

Every consumer repo needs its own `pyrightconfig.json` — `check` runs `type_check` unconditionally
(no allowances), so type-check config must exist everywhere `check` runs.

`inv dev-env.setup` is the one command to run once after cloning: `venv.create` (syncs `.venv` from
`uv.lock`) + `direnv.allow` + `agents.claude-hook` (wiring Claude Code's Bash tool to auto-activate
the venv too, no-ops if the repo has no `.envrc`) — `dev_env.py` itself owns no logic, it's pure
orchestration of those three modules. `inv docs.build`/`docs.serve` assume `zensical` is installed
— add it as a project `docs` dependency group, it isn't a dependency of this package.

### venv/deps: lock-respecting, CI/docker-aware

`venv.sync` (and `venv.create`, its no-args first-time wrapper) always run `uv sync --locked` —
this fails loudly on a missing or stale `uv.lock` instead of uv's own default of silently
rewriting it. `inv deps.lock` is the _only_ task in this package that ever runs `uv lock`; every
other `deps.*`/`venv.*` task is read-only with respect to the lockfile.

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
package to the same `.venv` — no re-resolution, so the shipped container runs exactly the wheel
that could also go straight to `inv dist.publish`.

## Developing

```shell
uv sync
inv quality.precommit
```

This repo dogfoods its own tasks against itself (`tasks.py` is `from repo_tasks import ns` — the
same one-liner a consumer uses).

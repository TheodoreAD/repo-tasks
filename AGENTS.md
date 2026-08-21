# Agent instructions for repo-tasks

Cross-tool instructions for AI coding agents working in this repo. Universal conventions (sudo/ssh
askpass, Bash/allowlist discipline, cross-session memory policy) live in `~/AGENTS.md` — no need
to repeat them here, only what's specific to this repo.

## Build & test

`.envrc` puts `.venv/bin` on `PATH` — once direnv has activated (`direnv allow`, or
`inv dev-env.setup` the first time), `inv` runs directly with no `uv run` prefix needed.

- `inv quality.precommit` — fix then check; the one command to run before considering a change done.
- `inv quality.check` — CI-style gate alone, no mutations.
- `inv quality.type-check` / `inv quality.test` / etc. — individual tasks, see `inv -l`.

## Conventions

This repo dogfoods its own tasks (`tasks.py` is `from repo_tasks import ns`, same as any consumer).

One module per facility, named after what it owns (`venv.py`, `deps.py`, `direnv.py`, `agents.py`,
...) — not a broad grab-bag module. A module that only composes other modules' tasks into a
one-command entrypoint (`dev_env.py`'s `setup`) is fine and owns no logic of its own, but avoid
naming a module after the composite's purpose in a way that reads like it could own real
responsibilities that actually belong to `venv`/`deps`/`dist`/etc.

When one submodule needs a sibling's task (e.g. `dev_env.py` composing `venv.create` into its own
`pre=[...]`), import it as `from .sibling import name` — not `from . import sibling` and not
`import repo_tasks.sibling as sibling`. Since every module here is also wired into this package's
own `__init__.py`, those other two forms both trigger a `reportImportCycles` false positive in
basedpyright (the submodule ends up depending on `__init__.py` itself, which already depends on
it). `from .sibling import name` targets the submodule file directly and avoids it — see
`version.py`/`gitflow.py` for the existing pattern.

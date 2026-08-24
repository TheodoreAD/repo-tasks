# Agent instructions for repo-tasks

Cross-tool instructions for AI coding agents working in this repo. Universal conventions (sudo/ssh
askpass, Bash/allowlist discipline, cross-session memory policy) live in `~/AGENTS.md` — no need to
repeat them here, only what's specific to this repo.

## Build & test

`.envrc` puts `.venv/bin` on `PATH` — once direnv has activated (`direnv allow`, or
`inv dev-env.setup` the first time), `inv` runs directly with no `uv run` prefix needed.

- `inv quality.precommit` — fix then check; the one command to run before considering a change done.
- `inv quality.check` — CI-style gate alone, no mutations.
- `inv quality.type-check` / `inv test.unit` / etc. — individual tasks, see `inv -l`.

## Where things are written down

- `README.md` — what the tasks are and how to use them.
- `contributing/` — why they are built this way, and what was rejected. Read the relevant file
  before changing behavior it covers:
  - [`task-module-conventions.md`](contributing/task-module-conventions.md) — the rules every task
    module follows (never silently mutate, single-writer, no-op cleanly, zero-config defaults).
  - [`release-flow.md`](contributing/release-flow.md) — how gitflow is applied, and known bad
    states.
  - [`versioning.md`](contributing/versioning.md) — semver, grouping, and the python/docker/helm
    format split.
  - [`test-tiers.md`](contributing/test-tiers.md) — the unit / integration / clean-OS split and its
    fixtures.
- `plans/` — work not yet done. Anything unfinished belongs here, never as prose in the files above.
  Tagged so it can be found without opening files: `rg '^\s*[-*]?\s*\[DEFERRED:' plans/` for the
  backlog, `[NEEDS CLARIFICATION:` for open questions, `[UNVERIFIED:` for unproven claims.

## Conventions

This repo dogfoods its own tasks (`tasks.py` is `from repo_tasks import ns`, same as any consumer).

One module per facility, named after what it owns (`venv.py`, `deps.py`, `direnv.py`, `agents.py`,
...) — not a broad grab-bag module. A module that only composes other modules' tasks into a
one-command entrypoint (`dev_env.py`'s `setup`) is fine and owns no logic of its own, but avoid
naming a module after the composite's purpose in a way that reads like it could own real
responsibilities that actually belong to `venv`/`deps`/`dist`/etc.

The rest of the module-level rules — never silently mutate state, single-writer ownership of
`uv.lock` and version fields, no-op cleanly when an artifact kind is absent, name flags after what
they do — are in
[`contributing/task-module-conventions.md`](contributing/task-module-conventions.md), with the
reasoning and what was rejected.

When one submodule needs a sibling's task (e.g. `dev_env.py` composing `venv.create` into its own
`pre=[...]`), import it as `from .sibling import name` — not `from . import sibling` and not
`import repo_tasks.sibling as sibling`. Since every module here is also wired into this package's
own `__init__.py`, those other two forms both trigger a `reportImportCycles` false positive in
basedpyright (the submodule ends up depending on `__init__.py` itself, which already depends on it).
`from .sibling import name` targets the submodule file directly and avoids it — see
`version.py`/`gitflow.py` for the existing pattern.

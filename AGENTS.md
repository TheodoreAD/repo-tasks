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

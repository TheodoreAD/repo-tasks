#!/usr/bin/env bash
set -euo pipefail

# Get from a fresh clone (or a CI runner) to a working `inv`, nothing more — the one place a raw
# `uv` call is unavoidable, since there's no `inv` to bootstrap with yet. `uv run` syncs this
# checkout's own .venv (same command as manually running `uv sync`) and then runs `inv
# venv.create` inside it, which — via venv.py's own GITHUB_PATH registration — also adds
# .venv/bin to PATH for the rest of the job when run under GitHub Actions (a no-op locally).
# Every command after this one is a bare `inv <task>` call: `inv dev-env.setup` for the full local
# dev loop (direnv, Claude Code hook), `inv quality.check`/`inv quality.precommit` to run the
# quality gate, `inv -l` to see everything else.

command -v uv > /dev/null 2>&1 || {
  echo "uv not found on PATH — install uv first" >&2
  exit 1
}
uv run inv venv.create

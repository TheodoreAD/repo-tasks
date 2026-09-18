#!/usr/bin/env bash
# Local replica of the scaffoldapy canary CI job, run before writing the workflow that does it for
# real. Installs *this checkout* as the global repo-tasks uv tool inside a sandboxed HOME, then runs
# scaffoldapy's e2e tier against it. Nothing touches the real HOME, the real global tool install, or
# scaffoldapy's own working tree — the clone is a fresh one from GitHub, which is also what makes
# this measure scaffoldapy's `main` rather than whatever the local checkout happens to be on.
set -euo pipefail

REPO_TASKS=/home/tdumitrescu/projects/github.com-personal/repo-tasks
SANDBOX="$(dirname "$0")/canary"
SANDBOX="$(mkdir -p "$SANDBOX" && cd "$SANDBOX" && pwd)"

# Resolved against the real machine before HOME is faked — a cold uv cache or a re-downloaded
# interpreter would cost more than the whole run. Same two pins scaffoldapy's own isolated_home
# fixture keeps, for the same reason.
REAL_UV_CACHE="$(uv cache dir)"
REAL_UV_PYTHON="$(uv python dir)"

rm -rf "${SANDBOX:?}"/home "${SANDBOX:?}"/scaffoldapy
mkdir -p "$SANDBOX/home"

export HOME="$SANDBOX/home"
export UV_CACHE_DIR="$REAL_UV_CACHE"
export UV_PYTHON_INSTALL_DIR="$REAL_UV_PYTHON"
export PATH="$HOME/.local/bin:$PATH"
unset VIRTUAL_ENV PYTHONPATH XDG_CACHE_HOME XDG_CONFIG_HOME XDG_DATA_HOME XDG_STATE_HOME

echo "=== clone scaffoldapy main ==="
git clone --depth 1 https://github.com/TheodoreAD/scaffoldapy.git "$SANDBOX/scaffoldapy"
git -C "$SANDBOX/scaffoldapy" log -1 --format='scaffoldapy %h %ad %s' --date=short

echo "=== install this checkout as the global tool ==="
uv tool install --force --with-executables-from invoke "$REPO_TASKS"
command -v inv
command -v repo-tasks
python3 -c "import sys, subprocess; print(subprocess.run(['repo-tasks','--list'],capture_output=True,text=True).returncode)"

echo "=== scaffoldapy: dev-env.setup ==="
cd "$SANDBOX/scaffoldapy"
inv dev-env.setup

echo "=== scaffoldapy: test.integration ==="
PATH="$SANDBOX/scaffoldapy/.venv/bin:$PATH" inv test.integration

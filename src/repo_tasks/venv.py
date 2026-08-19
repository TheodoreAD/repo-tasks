"""Venv lifecycle tasks — never writes uv.lock. `deps.py` is the only module allowed to run
`uv lock`; every sync here passes --locked, so a stale/missing lock fails loudly instead of uv's
own default of silently rewriting it."""

import shutil
from pathlib import Path

from invoke import task

_VENV_DIR = Path(".venv")


@task(
    help={
        "no_editable": "Install the project (and workspace members) non-editable — CI/docker mode",
        "no_dev": "Skip the dev dependency group — slim runtime-only install",
        "no_install_project": "Sync only third-party dependencies, skipping the local project entirely",
    }
)
def sync(c, no_editable=False, no_dev=False, no_install_project=False):
    """Sync .venv from uv.lock (uv sync --locked). Fails loudly on a stale or missing lock
    instead of silently rewriting it — run `inv deps.lock` first if that happens."""
    cmd = "uv sync --locked"
    if no_editable:
        cmd += " --no-editable"
    if no_dev:
        cmd += " --no-dev"
    if no_install_project:
        cmd += " --no-install-project"
    c.run(cmd, echo=True)


@task(pre=[sync])
def create(c):
    """Create/refresh .venv from uv.lock — the first-time-after-clone entrypoint."""


@task
def delete(c):
    """Remove .venv."""
    if not _VENV_DIR.exists():
        print("[venv.delete] .venv not present — nothing to clean")
        return
    shutil.rmtree(_VENV_DIR)
    print("[venv.delete] .venv removed")


@task(help={"wheel": "Path (or glob) to the already-built wheel to install"})
def install_wheel(c, wheel="dist/*.whl"):
    """Install an already-built wheel into .venv with --no-deps. Pairs with a deps-only sync
    (venv.sync --no-install-project): adds only the project package on top, never re-resolving or
    touching any dependency that sync already installed."""
    c.run(f"uv pip install --no-deps {wheel}", echo=True)

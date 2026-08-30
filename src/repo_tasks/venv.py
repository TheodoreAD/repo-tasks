"""Venv lifecycle tasks — never writes uv.lock. `deps.py` is the only module allowed to run
`uv lock`; every sync here passes --locked, so a stale/missing lock fails loudly instead of uv's
own default of silently rewriting it."""

import os
import re
import shutil
from pathlib import Path

from invoke import Context, Exit, task

from .gitflow import _next_steps  # pyright: ignore[reportPrivateUsage]
from .projects import python_floor
from .requirements import NETWORK, requires

_VENV_DIR = Path(".venv")

_PYTHON_HELP = "Build .venv against this Python (e.g. 3.11), replacing it if it is on another version"


def _venv_python() -> str | None:
    """The `major.minor` .venv was built with, or None when there is no venv (or an unreadable one).

    Read out of `pyvenv.cfg`'s `version_info` rather than by running `.venv/bin/python -V`: no
    subprocess, and it still answers for a venv too broken to execute — which is one of the states
    worth reporting rather than crashing on."""
    cfg = _VENV_DIR / "pyvenv.cfg"
    if not cfg.exists():
        return None
    match = re.search(r"^version_info\s*=\s*(\d+\.\d+)", cfg.read_text(), re.MULTILINE)
    return match.group(1) if match else None


def _register_github_path(bin_dir: Path) -> None:
    """CI's equivalent of direnv: GitHub Actions has no shell-hook mechanism, so a freshly-synced
    .venv/bin needs to be added to PATH explicitly for later steps' bare `inv <task>` calls (e.g.
    quality.check's ruff/pytest/basedpyright) to resolve it — appending to $GITHUB_PATH is the
    documented way a step extends PATH for the rest of the job. No-ops outside GitHub Actions
    (GITHUB_PATH unset), so this is always safe to call unconditionally after a sync."""
    github_path = os.environ.get("GITHUB_PATH")
    if not github_path:
        return
    with Path(github_path).open("a") as f:
        f.write(f"{bin_dir.resolve()}\n")


@requires(NETWORK)
@task(
    help={
        "project": "Workspace member to sync (default: the whole workspace root)",
        "no_editable": "Install the project (and workspace members) non-editable — CI/docker mode",
        "no_dev": "Skip the dev dependency group — slim runtime-only install",
        "no_install_project": "Sync only third-party dependencies, skipping the local project entirely",
        "python": _PYTHON_HELP,
    }
)
def sync(
    c: Context,
    project: str | None = None,
    no_editable: bool = False,
    no_dev: bool = False,
    no_install_project: bool = False,
    python: str | None = None,
):
    """Sync .venv from uv.lock (uv sync --locked). Fails loudly on a stale or missing lock
    instead of silently rewriting it — run `inv deps.lock` first if that happens.

    `--project` narrows the sync to one workspace member's own dependencies (uv's `--package`),
    which is what a runtime image for that member wants: the root project's dependency tree has
    no business in it. Omitted, the behaviour is unchanged — the workspace root, as before.

    `--python` names the interpreter to build against. Omitted — the default, and what every
    existing caller gets — nothing is said and uv keeps whatever .venv already has, or picks the
    newest interpreter satisfying `requires-python` when there is no venv yet. Given a version, uv
    removes a venv on any other version and recreates it, in that order, so an interpreter it cannot
    obtain leaves the existing venv untouched rather than deleting it first and failing after."""
    cmd = "uv sync --locked"
    if project:
        cmd += f" --package {project}"
    if python:
        cmd += f" --python {python}"
    if no_editable:
        cmd += " --no-editable"
    if no_dev:
        cmd += " --no-dev"
    if no_install_project:
        cmd += " --no-install-project"
    c.run(cmd, echo=True)
    _register_github_path(_VENV_DIR / "bin")


@task(pre=[sync])
def create(c: Context):
    """Create/refresh .venv from uv.lock — the first-time-after-clone entrypoint."""


@task
def delete(c: Context):
    """Remove .venv."""
    if not _VENV_DIR.exists():
        print("[venv.delete] .venv not present — nothing to clean")
        return
    shutil.rmtree(_VENV_DIR)
    print("[venv.delete] .venv removed")


@task
def check(c: Context):
    """Report whether .venv's Python is the one this project declares in `requires-python`. Reads
    only — exits nonzero when they differ, naming `venv.recreate` as the fix.

    The mismatch is silent by construction and outlives whatever caused it: uv builds a venv with
    the newest interpreter satisfying the floor, so a repo declaring `>=3.11` gets 3.14 and every
    local run — pytest included — exercises a version no consumer is promised. Since `configs.pull`
    started deriving `pythonVersion` from the same declaration, the type checker and the test run
    disagree about which Python this project is, which is the state worth being able to see.

    Deliberately not in `quality.check`. CI's gate job builds its venv from whatever uv picks and
    would fail this on every run, and a developer's local interpreter choice is not something a
    shared gate should have an opinion about — the four-interpreter unit matrix is what actually
    holds `requires-python` to its claim."""
    declared = python_floor()
    actual = _venv_python()
    if declared is None:
        print("[venv.check] no requires-python declared — nothing to check against")
        return
    if actual is None:
        print(f"[venv.check] no .venv (this project declares Python {declared})")
        _next_steps("inv venv.create")
        raise Exit(code=1)
    if actual == declared:
        print(f"[venv.check] .venv is on Python {actual}, as declared")
        return
    print(f"[venv.check] .venv is on Python {actual}, but this project declares {declared}")
    _next_steps(f"inv venv.recreate  # rebuild .venv on Python {declared}")
    raise Exit(code=1)


@requires(NETWORK)
@task(help={"python": "Rebuild against this Python instead of the floor this project declares"})
def recreate(c: Context, python: str | None = None):
    """Rebuild .venv against the Python this project declares in `requires-python` — the fix
    `venv.check` names, and the way to move a venv that was created on the wrong interpreter.

    Not `delete` then `create`: uv resolves the interpreter first and only then swaps the venv, so a
    version it cannot obtain leaves the existing one intact (measured — a request below the declared
    floor is refused outright, with the old venv still in place), whereas deleting first would strand
    the project with no venv and no `inv` in it. `venv.delete` stays for actually wanting it gone.

    Nothing calls this on your behalf. `venv.create` still lets uv choose, because that is what CI's
    unit matrix steers through `setup-uv`'s `python-version` — a floor hardcoded there would quietly
    collapse four interpreters into four runs of the same one."""
    target = python or python_floor()
    if target is None:
        raise Exit("[venv.recreate] this project declares no requires-python — name a version with --python")
    sync(c, python=target)
    print(f"[venv.recreate] .venv is on Python {target}")


@requires(NETWORK)
@task(help={"wheel": "Path (or glob) to the already-built wheel to install"})
def install_wheel(c: Context, wheel: str = "dist/*.whl"):
    """Install an already-built wheel into .venv with --no-deps. Pairs with a deps-only sync
    (venv.sync --no-install-project): adds only the project package on top, never re-resolving or
    touching any dependency that sync already installed."""
    c.run(f"uv pip install --no-deps {wheel}", echo=True)

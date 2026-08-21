"""Dogfoods this repo's own quality tasks against itself — the exact same wiring
every consumer repo uses (see README.md)."""

import difflib
from pathlib import Path

from invoke import task

from repo_tasks import ns
from repo_tasks.configs import _CONFIG_FILES

__all__ = ["ns"]


@task(help={"apply": "Write root -> package (default: print-only diff)"})
def configs_promote(c, apply=False):
    """Diff this repo's own root config files against src/repo_tasks/configs/* (the shipped
    baseline) — print-only by default; --apply writes root -> package once a root-level tuning
    is ready to ship to every consumer. The other direction from `configs.pull`: this repo is the
    one place root and package are allowed to diverge in-flight (see AGENTS.md)."""
    package_dir = Path("src/repo_tasks/configs")
    changed = False
    for name in _CONFIG_FILES:
        root_text = Path(name).read_text()
        package_path = package_dir / name
        package_text = package_path.read_text() if package_path.exists() else ""
        if root_text == package_text:
            continue
        changed = True
        if apply:
            package_path.write_text(root_text)
            print(f"[configs-promote] {name}: root -> package")
            continue
        print(f"[configs-promote] {name} differs:")
        lines = difflib.unified_diff(
            package_text.splitlines(keepends=True),
            root_text.splitlines(keepends=True),
            fromfile=f"{name} (package)",
            tofile=f"{name} (root)",
        )
        print("".join(lines))
    if not changed:
        print("[configs-promote] root already matches package")


# invoke's @task decorator has no type stub, so pyright falls back to the plain undecorated
# function signature for anything decorated with it — add_task's `task: Task` parameter doesn't
# tolerate that the way ns's own Collection(...) constructor call does (see __init__.py).
ns.add_task(configs_promote)  # pyright: ignore[reportArgumentType]

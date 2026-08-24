"""Dogfoods this repo's own quality tasks against itself — the exact same wiring
every consumer repo uses (see README.md)."""

import difflib
from pathlib import Path
from typing import cast

from invoke import Collection, task

from repo_tasks import ns
from repo_tasks.configs import _CONFIG_FILES

__all__ = ["ns"]


@task(help={"apply": "Write root -> package (default: print-only diff)"})
def promote(c, apply=False):
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
            print(f"[configs.promote] {name}: root -> package")
            continue
        print(f"[configs.promote] {name} differs:")
        lines = difflib.unified_diff(
            package_text.splitlines(keepends=True),
            root_text.splitlines(keepends=True),
            fromfile=f"{name} (package)",
            tofile=f"{name} (root)",
        )
        print("".join(lines))
    if not changed:
        print("[configs.promote] root already matches package")


# Added into the shipped `configs` collection rather than as a top-level task: `promote` is the
# other direction of `configs.pull` and reads as one subject with two verbs. It stays out of the
# package itself (see configs.py) — this is repo-tasks' own tasks.py, so the task exists only here.
#
# Two separate pyright accommodations, both pre-existing in kind: invoke types
# Collection.collections loosely (hence the cast), and its @task decorator has no type stub, so
# pyright sees the plain undecorated function where add_task wants a Task (hence the ignore).
cast(Collection, ns.collections["configs"]).add_task(promote, name="promote")  # pyright: ignore[reportArgumentType]

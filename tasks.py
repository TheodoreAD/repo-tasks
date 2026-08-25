"""Dogfoods this repo's own quality tasks against itself — the exact same wiring
every consumer repo uses (see README.md)."""

import difflib
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Exit, task

from repo_tasks import ns
from repo_tasks.configs import _CONFIG_FILES  # pyright: ignore[reportPrivateUsage] — this repo's own dev task

__all__ = ["ns"]


@task(
    help={
        "file": f"The one config file to write root -> package, required with --apply ({', '.join(_CONFIG_FILES)})",
        "apply": "Write root -> package for --file (default: print-only diff of every file)",
    }
)
def promote(c: Context, file: str | None = None, apply: bool = False):
    """Diff this repo's own root config files against src/repo_tasks/configs/* (the shipped
    baseline) — print-only by default; `--apply --file <name>` writes that one file root ->
    package once a root-level tuning is ready to ship to every consumer. Never more than the file
    named: the print-only diff lists everything that differs so a second in-flight tuning is seen,
    not promoted alongside. The other direction from `configs.pull`: this repo is the one place
    root and package are allowed to diverge in-flight (see AGENTS.md)."""
    package_dir = Path("src/repo_tasks/configs")
    if file is not None and file not in _CONFIG_FILES:
        raise Exit(f"[configs.promote] --file must be one of {', '.join(_CONFIG_FILES)}, got {file!r}")
    if apply:
        if file is None:
            raise Exit("[configs.promote] --apply writes exactly one file — name it with --file <name>")
        root_text = Path(file).read_text()
        package_path = package_dir / file
        if package_path.exists() and package_path.read_text() == root_text:
            print(f"[configs.promote] {file} already matches package")
            return
        package_path.write_text(root_text)
        print(f"[configs.promote] {file}: root -> package")
        return
    changed = False
    for name in _CONFIG_FILES if file is None else [file]:
        root_text = Path(name).read_text()
        package_path = package_dir / name
        package_text = package_path.read_text() if package_path.exists() else ""
        if root_text == package_text:
            continue
        changed = True
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
# One pyright accommodation: invoke types Collection.collections loosely, hence the cast. (`promote`
# itself is a properly typed Task thanks to invoke-stubs — see the quality dependency group.)
cast(Collection, ns.collections["configs"]).add_task(promote, name="promote")

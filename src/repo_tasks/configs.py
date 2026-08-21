"""Canonical tool config distribution — ruff.toml/pyrightconfig.json/dprint.json/pytest.ini/
.editorconfig, shipped as package data so a fix or improvement lands once and reaches every
consumer deliberately (a pinned dependency bump), instead of being hand-copied and silently
drifting per repo. `pull`/`diff` read from the installed package by default, or from
`--source git:<url>`/`local:<path>` to stage a candidate from elsewhere instead. The reverse
direction — promoting a repo's own tuned root config into the shipped baseline — is
`configs_promote` in repo-tasks' own `tasks.py`, not exported here: every consumer's `check`
still runs unconditionally against whatever `pull` last wrote, no per-repo `configs.local.toml`
override exists today (see plans/2026-08-14-python-repo-scaffolding.md §D)."""

import difflib
import json
import re
import subprocess
import tempfile
from importlib import resources
from pathlib import Path

from invoke import Exit, task

_CONFIG_FILES = ["ruff.toml", "pyrightconfig.json", "dprint.json", "pytest.ini", ".editorconfig"]

_SOURCE_HELP = "Override the config source: git:<url> or local:<path> (default: the installed repo_tasks package)"

_PYRIGHT_INCLUDE_RE = re.compile(r'"include":\s*\[(?P<items>[^\]]*)\]')


def _source_dir(source: str | None) -> Path:
    if source is None:
        return Path(str(resources.files("repo_tasks"))) / "configs"
    if source.startswith("git:"):
        url = source.removeprefix("git:")
        clone_dir = Path(tempfile.mkdtemp(prefix="repo-tasks-configs-"))
        subprocess.run(["git", "clone", "--depth", "1", url, str(clone_dir)], check=True)
        return clone_dir
    if source.startswith("local:"):
        return Path(source.removeprefix("local:")).expanduser()
    raise ValueError(f"--source must start with 'git:' or 'local:', got {source!r}")


def _resolve_content(name: str, src_dir: Path) -> str:
    """Read one canonical config file's content, applying the one piece of per-target
    resolution this mechanism needs: pyrightconfig.json's `include` lists every source layout
    this family uses (src/tests for a src-layout consumer, tasks/tasks.py for a flat-layout one
    or any consumer's own entry point) so nothing has to be hand-tuned per repo — but unlike
    `exclude`, basedpyright hard-errors (exit 3, "File or directory ... does not exist") on an
    `include` entry that isn't a real path. Filtered down to whichever candidates actually exist
    in the pull target before writing, so the canonical file stays the single declarative source
    of truth without every consumer needing its own subset by hand.
    """
    text = (src_dir / name).read_text()
    if name != "pyrightconfig.json":
        return text
    match = _PYRIGHT_INCLUDE_RE.search(text)
    if not match:
        return text
    candidates: list[str] = re.findall(r'"([^"]+)"', match.group("items"))
    existing: list[str] = [c for c in candidates if Path(c).exists()]
    new_items = ", ".join(json.dumps(c) for c in existing)
    return text[: match.start()] + f'"include": [{new_items}]' + text[match.end() :]


@task(help={"source": _SOURCE_HELP})
def pull(c, source=None):
    """Materialize ruff.toml/pyrightconfig.json/dprint.json/pytest.ini/.editorconfig from the
    canonical source into this repo's root. Overwrites unconditionally."""
    src_dir = _source_dir(source)
    for name in _CONFIG_FILES:
        Path(name).write_text(_resolve_content(name, src_dir))
        print(f"[configs.pull] {name} pulled")


@task(help={"source": _SOURCE_HELP})
def diff(c, source=None):
    """Show what `configs.pull` would change, without writing anything. Exits nonzero if
    anything differs."""
    src_dir = _source_dir(source)
    changed = False
    for name in _CONFIG_FILES:
        src_text = _resolve_content(name, src_dir)
        dst_path = Path(name)
        dst_text = dst_path.read_text() if dst_path.exists() else ""
        if src_text == dst_text:
            continue
        changed = True
        print(f"[configs.diff] {name} differs:")
        lines = difflib.unified_diff(
            dst_text.splitlines(keepends=True),
            src_text.splitlines(keepends=True),
            fromfile=f"{name} (current)",
            tofile=f"{name} (pulled)",
        )
        print("".join(lines))
    if not changed:
        print("[configs.diff] up to date")
        return
    raise Exit(code=1)

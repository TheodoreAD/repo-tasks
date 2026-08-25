"""Canonical tool config distribution — ruff.toml/pyrightconfig.json/dprint.json/pytest.ini/
.editorconfig, shipped as package data so a fix or improvement lands once and reaches every
consumer deliberately (a pinned dependency bump), instead of being hand-copied and silently
drifting per repo. Every file is copied verbatim — nothing is resolved per consumer, so a pulled
root is byte-identical to the package copy (pyrightconfig.json's `include` globs are what make
that possible; see the comment in that file). `pull`/`diff` read from the installed package by
default, or from `--source git:<url>`/`local:<path>` to stage a candidate from elsewhere instead.
The reverse direction — promoting a repo's own tuned root config into the shipped baseline — is
`configs.promote` in repo-tasks' own `tasks.py`, not exported here: every consumer's `check`
still runs unconditionally against whatever `pull` last wrote, no per-repo `configs.local.toml`
override exists today (see plans/2026-08-14-python-repo-scaffolding.md §D).

This module also owns the other half of what a consumer snapshots: the `repo-tasks-quality`
dependency manifest. `ensure_deps` splices it in, and `require_tool` — imported by the gate steps
in `quality.py`/`testing.py` — turns a binary that manifest should have provided into the command
that fixes its absence. Both read the same packaged `pyproject.toml`, so there is one manifest and
no second list to keep in step."""

import difflib
import re
import shutil
import subprocess
import tempfile
import tomllib
from importlib import resources
from pathlib import Path
from typing import cast

from invoke import Context, Exit, task

from .gitflow import _next_steps  # pyright: ignore[reportPrivateUsage]

_CONFIG_FILES = ["ruff.toml", "pyrightconfig.json", "dprint.json", "pytest.ini", ".editorconfig"]

_SOURCE_HELP = "Override the config source: git:<url> or local:<path> (default: the installed repo_tasks package)"

_DEV_ARRAY_RE = re.compile(r"dev\s*=\s*\[(?P<items>.*?)\]", re.DOTALL)
_BARE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+")

_DUMMY_PYPROJECT_TEMPLATE = """\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[tool.uv]
package = false

[dependency-groups]
dev = [
{deps}
]
"""


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


# Every binary a gate step shells out to, mapped to the `repo-tasks-quality` entry providing it.
# Spelled out rather than derived: four of the seven distributions are named differently from the
# tool they install (`shfmt-py` -> `shfmt`), and the whole point of the message is to name the
# entry a consumer has to add. test_configs.py asserts every value is really in the manifest.
_GATE_TOOL_DISTRIBUTIONS = {
    "actionlint": "actionlint-py",
    "basedpyright": "basedpyright",
    "dprint": "dprint-py",
    "pytest": "pytest",
    "ruff": "ruff",
    "shellcheck": "shellcheck-py",
    "shfmt": "shfmt-py",
}

_DEV_GROUP_FIX = (
    "repo-tasks configs.ensure-deps  # splice in whatever repo-tasks-quality has grown since",
    "inv deps.lock                   # re-resolve uv.lock, then review the diff",
    "inv venv.sync",
)


def require_tool(tool: str) -> None:
    """Preflight a gate step's binary, stopping with the command that fixes it instead of leaving
    the caller the shell's bare exit 127.

    The failure this exists for, measured 2026-08-24: `quality.workflow_check` and its `actionlint`
    entry landed together, every consumer's dev group was a snapshot from before the entry existed,
    and CI failed with `actionlint: command not found` on every push for a day with nothing linking
    the message back to the drift that caused it."""
    if shutil.which(tool) is not None:
        return
    distribution = _GATE_TOOL_DISTRIBUTIONS.get(tool, tool)
    print(
        f"[configs] {tool} not found on PATH — {distribution} is not installed in this project's "
        "environment. repo-tasks ships it in the repo-tasks-quality manifest, so either this "
        "project's dependency-groups.dev is behind that manifest or .venv is out of sync with the lock."
    )
    _next_steps(*_DEV_GROUP_FIX)
    raise Exit(code=1)


@task(help={"source": _SOURCE_HELP})
def pull(c: Context, source: str | None = None):
    """Materialize ruff.toml/pyrightconfig.json/dprint.json/pytest.ini/.editorconfig from the
    canonical source into this repo's root, verbatim. Overwrites unconditionally."""
    src_dir = _source_dir(source)
    for name in _CONFIG_FILES:
        Path(name).write_text((src_dir / name).read_text())
        print(f"[configs.pull] {name} pulled")


@task(help={"source": _SOURCE_HELP})
def diff(c: Context, source: str | None = None):
    """Show what `configs.pull` would change, without writing anything. Exits nonzero if
    anything differs."""
    src_dir = _source_dir(source)
    changed = False
    for name in _CONFIG_FILES:
        src_text = (src_dir / name).read_text()
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


def _own_pyproject_data() -> dict[str, object]:
    """The real pyproject.toml this repo_tasks install came from — force-included as package data
    for a real (non-editable) install (see [tool.hatch.build.targets.wheel.force-include]), but an
    editable dev install (this repo's own dev loop) never runs that build step, so fall back to the
    literal source-tree file two levels up from the installed package (src/repo_tasks/../.. is the
    repo root) in that case."""
    packaged = resources.files("repo_tasks") / "pyproject.toml"
    if packaged.is_file():
        return tomllib.loads(packaged.read_text())
    fallback = Path(str(resources.files("repo_tasks"))).parent.parent / "pyproject.toml"
    return tomllib.loads(fallback.read_text())


def _quality_deps() -> list[str]:
    """The exact version-constrained dependency strings repo-tasks itself uses and tests its
    quality tooling against (dependency-groups.quality) — the single source of truth `ensure_deps`
    injects into a consumer, never a second hand-maintained list."""
    groups = cast(dict[str, object], _own_pyproject_data()["dependency-groups"])
    return cast(list[str], groups["repo-tasks-quality"])


def _bare_name(spec: str) -> str:
    match = _BARE_NAME_RE.match(spec)
    return match.group(0).lower() if match else spec.lower()


def _derive_project_name(c: Context) -> str:
    """git remote's repo name, falling back to the current directory's name if there's no remote
    (or no git repo at all) — normalized to a valid project name."""
    result = c.run("git config --get remote.origin.url", hide=True, warn=True)
    if result.ok and result.stdout.strip():
        name = result.stdout.strip().rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    else:
        name = Path.cwd().name
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@task
def ensure_deps(c: Context):
    """Ensure this project's pyproject.toml declares every quality-tooling dependency repo-tasks
    needs (sourced from repo-tasks' own dependency-groups.quality — never a second,
    separately-maintained list) — creates a minimal pyproject.toml first if none exists. Additive
    only: never touches an entry already present (by bare package name, ignoring version), so
    existing lock files and CI runs stay stable. Never adds `repo-tasks`/`invoke` themselves —
    those only ever belong in repo-tasks' own main dependencies; a project that wants them anyway
    is free to add them by hand. Run `inv deps.lock` and review/commit the diff afterward — this
    task never touches uv.lock itself."""
    canonical = _quality_deps()
    pyproject_path = Path("pyproject.toml")

    if not pyproject_path.exists():
        name = _derive_project_name(c)
        deps = "\n".join(f'  "{dep}",' for dep in canonical)
        pyproject_path.write_text(_DUMMY_PYPROJECT_TEMPLATE.format(name=name, deps=deps))
        print(f"[configs.ensure-deps] created pyproject.toml (project name: {name!r})")
        for dep in canonical:
            print(f"[configs.ensure-deps] {_bare_name(dep)} added")
        tasks_py = Path("tasks.py")
        if not tasks_py.exists() and not Path("tasks").exists():
            # Bare `inv <task>` needs a tasks.py/tasks/ to find any collection at all — without
            # this, everything past this point (`inv deps.lock`, `inv quality.check`, ...) would
            # be unreachable except through the standalone `repo-tasks` script, same as
            # `configs.ensure-deps` itself was before it got nested there too.
            # repo_tasks is deliberately never added to this project's own dependencies (see
            # ensure_deps' docstring) — it's only ever resolvable via the globally-installed
            # `repo-tasks` tool, invisible to a type checker that only sees this project's own
            # venv, hence the pyright suppression. Same shape scaffoldapy's own template/tasks.py
            # uses, for the same reason.
            tasks_content = 'from repo_tasks import ns  # pyright: ignore[reportMissingImports]\n\n__all__ = ["ns"]\n'
            tasks_py.write_text(tasks_content)
            print("[configs.ensure-deps] created tasks.py")
        # A repo with no pyproject.toml also has none of the canonical tool configs
        # (ruff.toml/dprint.json/pyrightconfig.json/pytest.ini/.editorconfig) — `inv quality.check`
        # needs those to actually run, not just the dependencies.
        pull(c, source=None)
        return

    text = pyproject_path.read_text()
    match = _DEV_ARRAY_RE.search(text)
    if not match:
        raise Exit(
            "[configs.ensure-deps] no `dependency-groups.dev` array found in pyproject.toml — add one by hand first"
        )

    existing_specs: list[str] = re.findall(r'"([^"]+)"', match.group("items"))
    present = {_bare_name(s) for s in existing_specs}
    missing = [dep for dep in canonical if _bare_name(dep) not in present]

    for dep in canonical:
        status = "added" if _bare_name(dep) in {_bare_name(m) for m in missing} else "already present"
        print(f"[configs.ensure-deps] {_bare_name(dep)} {status}")

    if not missing:
        return

    insertion = "".join(f'  "{dep}",\n' for dep in missing)
    if not match.group("items").strip():
        # `dev = []` (dprint's own preferred empty shape) or `dev = [\n]`: splicing after the
        # opening bracket would leave the first entry on the bracket's line, which dprint rejects.
        # Rebuild the whole array in the one multi-line shape dprint accepts — this runs before
        # any venv exists, so there is no formatter available afterwards to clean it up.
        pyproject_path.write_text(text[: match.start()] + f"dev = [\n{insertion}]" + text[match.end() :])
        return
    insert_at = match.end("items")
    pyproject_path.write_text(text[:insert_at] + insertion + text[insert_at:])

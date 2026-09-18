"""Conventions this package holds itself to that no linter enforces.

Each one here is a rule `contributing/` states in prose, with the check that would otherwise be a
sentence telling the next reader to re-derive it. That is the whole admission rule: a convention
with a mechanical check belongs in its tool's config (ruff, basedpyright), and a convention with
neither a tool nor a check is an assertion.
"""

import ast
import re
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

_REPO_ROOT = Path(__file__).parents[2]
_PACKAGE = _REPO_ROOT / "src" / "repo_tasks"
_TESTS = Path(__file__).parents[1]

# The floor the household rule puts this package on, and the reason it is a literal here rather than
# something derived. See the test that reads it.
_LIBRARY_FLOOR = "3.11"

_TEXT_IO = frozenset({"read_text", "write_text"})


def _unencoded_calls(tree: ast.AST) -> list[int]:
    """Line numbers of text-mode file reads and writes that name no encoding.

    `open` counts only in text mode: an `encoding` argument is an error on a binary one, and
    `projects.py` opens `pyproject.toml` as binary for `tomllib` by design."""
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if any(keyword.arg == "encoding" for keyword in node.keywords):
            continue
        if node.func.attr in _TEXT_IO:
            found.append(node.lineno)
        elif node.func.attr == "open":
            mode = node.args[0] if node.args else None
            if isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" not in mode.value:
                found.append(node.lineno)
    return found


@pytest.mark.parametrize("root", [_PACKAGE, _TESTS], ids=["package", "tests"])
def test_every_text_read_and_write_names_its_encoding(root: Path):
    """The rule is `contributing/task-module-conventions.md`, "Every file read and write names its
    encoding" — and nothing enforces it: ruff's `PLW1514` is preview-only, so selecting it means
    turning preview on in a config every consumer pulls.

    This is the walk that document describes, committed rather than described, because the 182 call
    sites it swept and the zero it confirmed are both numbers somebody has to be able to re-derive.
    The suite is checked as well as the package: a test writing a config file for a task to read is
    the same hazard as the task writing one."""
    offenders = [
        f"{path.relative_to(root.parent)}:{line}"
        for path in sorted(root.rglob("*.py"))
        for line in _unencoded_calls(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert not offenders, "text IO without an explicit encoding: " + ", ".join(offenders)


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _project_table() -> dict[str, object]:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as f:
        return cast(dict[str, object], cast(dict[str, object], tomllib.load(f))["project"])


def _requires_python_floor() -> str:
    return str(_project_table()["requires-python"]).removeprefix(">=").strip()


def _classifier_floor() -> str:
    prefix = "Programming Language :: Python :: "
    declared = [
        classifier.removeprefix(prefix)
        for classifier in cast(list[str], _project_table()["classifiers"])
        if classifier.startswith(prefix)
    ]
    return min(declared, key=_version_key, default="")


def _python_version_file_floor() -> str:
    return (_REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()


def _ci_matrix_floor() -> str:
    """The lowest entry of ci.yml's unit-tier matrix. Parsed with a regex rather than a YAML
    library: this suite has no YAML dependency, adding one to read a single list would put it in
    every consumer's dev group, and the line it reads is one this repo writes."""
    workflow = (_REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"python-version:\s*\[([^\]]+)\]", workflow)
    return min(re.findall(r'"([0-9.]+)"', matrix.group(1)), key=_version_key, default="") if matrix else ""


@pytest.mark.parametrize(
    ("source", "read"),
    [
        ("pyproject.toml requires-python", _requires_python_floor),
        ("pyproject.toml classifiers", _classifier_floor),
        (".python-version", _python_version_file_floor),
        (".github/workflows/ci.yml unit matrix", _ci_matrix_floor),
    ],
)
def test_every_declaration_of_the_python_floor_agrees_on_the_library_tier(source: str, read: Callable[[], str]):
    """3.11, in four files, none of which can see the others.

    The household rule, stated 2026-08-29 and restated twice since: 3.11 is the floor for this
    package, for libraries, and for anything someone else installs into their own environment;
    applications start on 3.14. The axis is what stands between the code and the interpreter, and
    for this package it is somebody else's resolver.

    The reason it is library tier rather than local tooling is the one worth keeping, settled by the
    user 2026-09-18: it can be reached as a user-wide `uv tool` install *and* be resolved into a
    project's own venv — `invoke-stubs` and `power-user-linux-setup` both take it as a dependency —
    so compatibility has to hold for the second case even though the first is the usual one. A repo
    that is usually a tool but can be a dependency is a dependency. Raising the floor here is a
    breaking change on a machine nobody here will hear about.

    A literal rather than a consistency check against `requires-python`, deliberately. A test that
    only asked the four to agree would pass on a coordinated move to 3.12, which is precisely the
    move the rule exists to stop; this way the constant is the deliberate act, and
    `plans/2026-08-29-python-floor-in-the-shipped-configs.md` is where the reason for changing it
    would go.

    The classifiers and the CI matrix name the floor as their _lowest_ entry, not their only one —
    this package supports 3.11 through 3.14 and tests all four. What is pinned is where the range
    starts.

    [PITFALL: none of this reaches the `.venv` on a developer's machine, and that is where the rule
    is actually broken today. This repo pins 3.11 in `.python-version` and the venv is 3.14.5,
    because `UV_PYTHON=3.14` is exported machine-wide and uv ranks an environment variable above a
    project's pin. `inv venv.check` is what reports it; nothing in this file can.]"""
    assert read() == _LIBRARY_FLOOR, (
        f"{source} does not put this package's Python floor at {_LIBRARY_FLOOR}. This package is a "
        f"library — its floor is every consumer's floor. Raise it only deliberately, and move all "
        f"four declarations together."
    )

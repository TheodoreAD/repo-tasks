"""Conventions this package holds itself to that no linter enforces.

Each one here is a rule `contributing/` states in prose, with the check that would otherwise be a
sentence telling the next reader to re-derive it. That is the whole admission rule: a convention
with a mechanical check belongs in its tool's config (ruff, basedpyright), and a convention with
neither a tool nor a check is an assertion.
"""

import ast
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).parents[2] / "src" / "repo_tasks"
_TESTS = Path(__file__).parents[1]

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

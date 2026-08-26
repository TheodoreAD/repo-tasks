"""Enforces the `@requires` convention: a task that shells out to something external has to say so.

Derived rather than curated. The check reads each module's source with `ast`, collects the command
strings each task builds, and maps their leading words onto requirements — so a new task that runs
`docker build` without declaring DOCKER fails here, which is the case a hand-maintained list of
"tasks that need things" would silently miss.

Two limits, both deliberate. It only sees string literals inside the task's own body, so a task
whose command is built in a module-level helper — or that reaches the network through a library
rather than a subprocess, like `dist.list-versions` and the container fixtures — must declare its
requirements by hand; the check asserts that what it derives is *covered*, never that a declaration
is unnecessary. And a gate step is held to the stronger rule: `quality.check`'s chain must derive no
requirements at all, since the whole point of that chain is running offline in any consumer.
"""

import ast
from pathlib import Path

import pytest

from repo_tasks import quality, requirements
from repo_tasks.requirements import DOCKER, GH, NETWORK

_SRC = Path("src/repo_tasks")

# Longest matching prefix wins, so a local special case can sit in front of a broader network one.
_COMMAND_REQUIREMENTS: dict[str, frozenset[str]] = {
    "docker ": frozenset({DOCKER}),
    # Trailing space, or this matches `actionlint` — which is a gate step, so the mistake surfaced
    # as "the offline gate needs Docker" the first time this ran.
    "act ": frozenset({DOCKER}),
    "gh ": frozenset({GH, NETWORK}),
    # `uv lock --check` verifies the committed lock against pyproject.toml and resolves nothing.
    "uv lock --check": frozenset(),
    "uv lock": frozenset({NETWORK}),
    "uv sync": frozenset({NETWORK}),
    "uv audit": frozenset({NETWORK}),
    "uv publish": frozenset({NETWORK}),
    "uv tool install": frozenset({NETWORK}),
    "uv pip install": frozenset({NETWORK}),
    "helm push": frozenset({NETWORK}),
    "git push": frozenset({NETWORK}),
    "git fetch": frozenset({NETWORK}),
    "git ls-remote": frozenset({NETWORK}),
}


def _literals(function: ast.FunctionDef) -> list[str]:
    """Every string literal in the body except the docstring, f-string prefixes included.

    The docstring is excluded on purpose: it is where a task *describes* needing Docker, and
    counting that would make the derivation agree with itself."""
    found: list[str] = []
    body = function.body[1:] if ast.get_docstring(function) else function.body
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.append(node.value)
            elif isinstance(node, ast.JoinedStr):
                # An f-string's literal chunks — `f"docker build -t {ref}"` contributes
                # "docker build -t ", which is the part that names the command.
                found.extend(
                    part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
    return found


def _derived(function: ast.FunctionDef) -> frozenset[str]:
    needed: set[str] = set()
    for literal in _literals(function):
        matches = [prefix for prefix in _COMMAND_REQUIREMENTS if literal.startswith(prefix)]
        if matches:
            needed |= _COMMAND_REQUIREMENTS[max(matches, key=len)]
    return frozenset(needed)


def _is_task(function: ast.FunctionDef) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "task":
            return True
    return False


def _tasks() -> list[tuple[str, ast.FunctionDef]]:
    found: list[tuple[str, ast.FunctionDef]] = []
    for path in sorted(_SRC.glob("*.py")):
        tree = ast.parse(path.read_text())
        found.extend(
            (f"repo_tasks.{path.stem}", node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and _is_task(node)
        )
    return found


_TASKS = _tasks()

_GATE_STEPS = {step.name for step in quality.check.pre}

_GATE_TASKS = [(module, function) for module, function in _TASKS if function.name in _GATE_STEPS]


def _test_id(value: object) -> str:
    """Name each parametrized case after the task, so a failure reads `... [docker_build]`."""
    return value.name if isinstance(value, ast.FunctionDef) else str(value)


def test_the_scan_finds_every_task():
    # Guards the derivation itself: an ast change that quietly matched nothing would make every
    # assertion below vacuous.
    assert len(_TASKS) > 50


@pytest.mark.parametrize(("module", "function"), _TASKS, ids=_test_id)
def test_task_declares_what_its_commands_need(module: str, function: ast.FunctionDef):
    derived = _derived(function)
    declared = requirements.declared(module, function.name)
    missing = derived - declared
    assert not missing, (
        f"{module}.{function.name} runs a command needing {sorted(missing)} without declaring it — "
        f"add @requires({', '.join(sorted(missing))}) above @task"
    )


def test_the_gate_chain_was_actually_found():
    # If the pre-chain stopped resolving to these names, the parametrization below would be empty
    # and would assert nothing at all.
    assert len(_GATE_TASKS) >= 5


@pytest.mark.parametrize(("module", "function"), _GATE_TASKS, ids=_test_id)
def test_gate_steps_need_nothing_external(module: str, function: ast.FunctionDef):
    assert not _derived(function), (
        f"{module}.{function.name} is in quality.check's chain and runs a command needing "
        f"{sorted(_derived(function))} — the gate must stay runnable offline in every consumer"
    )


def test_requires_rejects_a_requirement_outside_the_vocabulary():
    # A typo'd requirement that silently recorded nothing would make the enforcement above pass
    # while declaring the wrong thing.
    with pytest.raises(ValueError, match="unknown requirement"):
        requirements.requires("netwrok")


def test_declared_is_empty_for_a_task_that_declared_nothing():
    assert requirements.declared("repo_tasks.docs", "clean") == frozenset()


def test_declared_reports_what_a_task_asked_for():
    assert requirements.declared("repo_tasks.docker", "build") == frozenset({DOCKER})
    assert requirements.declared("repo_tasks.ci", "status") == frozenset({GH, NETWORK})

"""Enforces the `@requires` convention: a task that shells out to something external has to say so.

Derived rather than curated. The check reads each module's source with `ast`, collects the command
strings each task builds, and maps their leading words onto requirements — so a new task that runs
`docker build` without declaring DOCKER fails here, which is the case a hand-maintained list of
"tasks that need things" would silently miss.

**The scan follows a task into its module's own helpers**, transitively, because that is where the
commands actually live in the modules that have grown one. `selfinstall.stamp` reached the network
through `_remote_tags`, which runs `git ls-remote`, and went undeclared for as long as the
derivation stopped at the task body — while `update`, which reaches the same helper, happened to be
declared by hand. One of the two was right by luck, and nothing could tell which.

One limit remains, deliberately: a task reaching the network through a *library* rather than a
subprocess — `dist.list-versions`, the container fixtures — has no command string to read and must
declare by hand. The check asserts that what it derives is *covered*, never that a declaration is
unnecessary. And a gate step is held to the stronger rule: `quality.check`'s chain must derive no
requirements at all, helpers included, since the whole point of that chain is running offline in any
consumer.
"""

import ast
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from invoke import Context, Task

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


def _called_helpers(function: ast.FunctionDef, helpers: dict[str, ast.FunctionDef]) -> list[ast.FunctionDef]:
    """The module's own functions this one calls by bare name — `_remote_tags(c)`, not `c.run(...)`.

    Only same-module calls resolve, which is the whole scope: a cross-module helper is somebody
    else's task's business, and following imports would mean resolving them."""
    return [
        helpers[node.func.id]
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in helpers
    ]


def _derived(function: ast.FunctionDef, helpers: dict[str, ast.FunctionDef]) -> frozenset[str]:
    """What this task's commands need, following its module's helpers transitively.

    A visited set rather than a depth limit: mutual recursion between two helpers would otherwise
    hang the test suite rather than fail it."""
    needed: set[str] = set()
    seen: set[str] = set()
    pending = [function]
    while pending:
        current = pending.pop()
        if current.name in seen:
            continue
        seen.add(current.name)
        for literal in _literals(current):
            matches = [prefix for prefix in _COMMAND_REQUIREMENTS if literal.startswith(prefix)]
            if matches:
                needed |= _COMMAND_REQUIREMENTS[max(matches, key=len)]
        pending.extend(_called_helpers(current, helpers))
    return frozenset(needed)


def _is_task(function: ast.FunctionDef) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "task":
            return True
    return False


def _tasks() -> list[tuple[str, ast.FunctionDef, dict[str, ast.FunctionDef]]]:
    """Every task in the package, each carried with its own module's helper functions.

    The helpers travel with the task because the derivation needs them, and a module is the unit
    that resolves a bare name."""
    found: list[tuple[str, ast.FunctionDef, dict[str, ast.FunctionDef]]] = []
    for path in sorted(_SRC.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        helpers = {node.name: node for node in functions if not _is_task(node)}
        found.extend((f"repo_tasks.{path.stem}", node, helpers) for node in functions if _is_task(node))
    return found


_TASKS = _tasks()


def _gate_step_key(step: object) -> tuple[str, str]:
    """Where a gate step is written: (module, function name).

    Keyed on both, never the name alone. `check` names a gate step (`deps.check`), the gate itself
    (`quality.check`), and a Docker-daemon task (`docker.check`) — a bare-name match reported
    `docker.check` as a gate step that needs Docker, which is true of the task and false of the
    gate.

    `Task.pre` is typed as a list of unparameterized tasks, so the one cast here is what gives
    `.body.__module__` a known type; every entry in this repo's chain is a plain `Task`."""
    task = cast(Task[Callable[[Context], None]], step)
    return (task.body.__module__, task.name)


_GATE_STEPS = {_gate_step_key(step) for step in quality.check.pre}

_GATE_TASKS = [
    (module, function, helpers) for module, function, helpers in _TASKS if (module, function.name) in _GATE_STEPS
]


def _test_id(value: object) -> str:
    """Name each parametrized case after the task, so a failure reads `... [docker_build]`.

    The helper map is collapsed to a word: it is an input to the derivation and says nothing about
    which case failed, while its repr is several kilobytes of dumped AST in every id and every
    failure line."""
    if isinstance(value, ast.FunctionDef):
        return value.name
    if isinstance(value, dict):
        return "helpers"
    return str(value)


def test_the_scan_finds_every_task():
    # Guards the derivation itself: an ast change that quietly matched nothing would make every
    # assertion below vacuous.
    assert len(_TASKS) > 50


@pytest.mark.parametrize(("module", "function", "helpers"), _TASKS, ids=_test_id)
def test_task_declares_what_its_commands_need(
    module: str, function: ast.FunctionDef, helpers: dict[str, ast.FunctionDef]
):
    derived = _derived(function, helpers)
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


@pytest.mark.parametrize(("module", "function", "helpers"), _GATE_TASKS, ids=_test_id)
def test_gate_steps_need_nothing_external(module: str, function: ast.FunctionDef, helpers: dict[str, ast.FunctionDef]):
    derived = _derived(function, helpers)
    assert not derived, (
        f"{module}.{function.name} is in quality.check's chain and runs a command needing "
        f"{sorted(derived)} — the gate must stay runnable offline in every consumer"
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

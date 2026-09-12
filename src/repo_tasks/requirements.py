"""What a task needs beyond a checkout, declared at the task itself.

`quality.check`'s steps are deterministic and offline by rule — that is what makes the gate runnable
anywhere, in every consumer. Everything else may reach the network, talk to a Docker daemon, or need
an authenticated CLI, and until now the only way to find out was to read the body. `@requires`
states it at the definition site, in a form a test can check rather than pattern-match out of prose.

    @requires(NETWORK)
    @task
    def audit(c: Context):
        ...

Above `@task`, never below: it takes the finished `Task` and hands the same object back, so the
`ParamSpec` typing invoke-stubs exists to provide survives untouched.

[PITFALL: the obvious mechanism is invoke's own `@task(klass=..., requires=...)`, and it costs the
typing. invoke rejects unknown kwargs outright (`TypeError`), so custom metadata needs a `Task`
subclass — and while invoke-stubs types `klass` itself, an *extra* keyword matches none of its
overloads, so `@task` silently degrades to an untyped decorator: measured, the decorated function's
`.body` becomes `Any` and `reportUntypedFunctionDecorator` fires, which `failOnWarnings` turns into
a failed gate. That is precisely the regression `invoke-stubs` was written to fix. A separate,
properly-typed decorator keeps both.]
"""

from collections.abc import Callable
from typing import ParamSpec, TypeVar, cast

from invoke import Task

P = ParamSpec("P")
R = TypeVar("R")

# Needs to reach something over the network — a package index, an advisory database, a git remote.
NETWORK = "network"

# Needs a reachable Docker daemon. `act` counts: it runs the workflow in containers.
DOCKER = "docker"

# Needs the `gh` CLI, authenticated against an account with access to the repo.
GH = "gh"

KNOWN = frozenset({NETWORK, DOCKER, GH})

_REGISTRY: dict[tuple[str, str], frozenset[str]] = {}


def _key(module: str, name: str) -> tuple[str, str]:
    return (module, name)


def requires(*needs: str) -> Callable[[Task[Callable[P, R]]], Task[Callable[P, R]]]:
    """Declare what a task needs beyond a checkout. Returns the task unchanged."""
    unknown = set(needs) - KNOWN
    if unknown:
        raise ValueError(f"unknown requirement(s) {sorted(unknown)} — expected some of {sorted(KNOWN)}")

    def apply(t: Task[Callable[P, R]]) -> Task[Callable[P, R]]:
        # Keyed off the undecorated function rather than the Task, so a test reading the module's
        # source with `ast` can look a task up by the name it is written under.
        _REGISTRY[_key(t.body.__module__, t.body.__name__)] = frozenset(needs)
        return t

    return apply


def declared(module: str, name: str) -> frozenset[str]:
    """What `name` in `module` declared, or an empty set if it declared nothing."""
    return _REGISTRY.get(_key(module, name), frozenset())


def effective(t: Task[Callable[P, R]]) -> frozenset[str]:
    """Everything running this task can need: its own declaration plus every pre-task's, transitively.

    **A composite declares nothing and is not thereby claiming to need nothing.** `inv configure`
    reaches the network twice — `dev_env.setup` for `uv sync`, `selfinstall.stamp` for the upstream
    tag list — and `inv quality.precommit` reaches nothing at all, and neither fact is written
    anywhere: both are properties of the chain. Restating a union at the composite would be a second
    copy of a derivable fact, wrong the first time a step in the chain gains a requirement and silent
    about it, which is the same objection this package makes to any hand-maintained list.

    So a composite is read, never written: this walks `pre` and answers. A `Call`-wrapped pre-task
    (`call(build, tag=...)`) resolves to the task it wraps — invoke permits it and nothing here uses
    it yet, but a union that silently skipped one would be worse than an error."""
    seen: set[tuple[str, str]] = set()
    found: set[str] = set()
    # `object`, and one cast per entry: `Task.pre` is typed `list[Task[Any] | Call]`, and reading
    # `.body` off an `Any`-parameterized task is exactly what `reportAny` is set to error on.
    pending: list[object] = [t]
    while pending:
        # `call(task, ...)` wraps rather than subclasses; a plain Task has no `.task` and is itself.
        entry = pending.pop()
        current = cast(Task[Callable[..., object]], getattr(entry, "task", entry))
        key = _key(current.body.__module__, current.body.__name__)
        if key in seen:
            continue
        seen.add(key)
        found |= _REGISTRY.get(key, frozenset())
        pending.extend(cast(list[object], current.pre))
    return frozenset(found)

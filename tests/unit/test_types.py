"""Pins the types this package *ships*, as a consumer sees them.

`py.typed` plus the `invoke-stubs` dependency make this package's types part of its public contract,
and `contributing/type-checking.md` records how much work that took — yet nothing asserted any of
it. basedpyright checking `src/` proves the code is internally consistent; it does not prove a
consumer's `@task`-decorated function keeps its signature, which is the thing that was broken before
`invoke-stubs` existed.

These assertions are checked by basedpyright, not at runtime: `assert_type` is a no-op when
executed, so a green pytest run says nothing here and is not meant to. The test that matters runs in
`inv quality.type-check`, where a regression in the stubs turns this file red. They live in the
suite anyway so the file is collected, imported, and therefore type-checked as test code rather than
drifting as an unreferenced snippet.

The failure mode being regression-tested, verbatim from that document: invoke's own
`def task(*args: Any, **kwargs: Any) -> Callable` erases the decorated function's type, so every
task body became `(...) -> Unknown` and every `from invoke import task` was a
`reportPrivateImportUsage`.
"""

from collections.abc import Callable
from typing import assert_type

# The idiomatic import itself is half the contract: without invoke-stubs' `__init__.pyi` re-exporting
# in `import X as X` form, this line is a reportPrivateImportUsage error under py.typed, which is
# what made consumers write `from invoke.tasks import task` instead.
from invoke import Collection, Context

from repo_tasks import deps, ns, quality


def test_task_decorator_preserves_a_plain_task_signature():
    # Declared, not asserted with assert_type: basedpyright reports `.body` as `(c: Context) -> None`
    # — the decorated function itself, parameter name and all — and a `Callable` type expression
    # cannot spell a parameter name, so assert_type can never match it. That precision is the point
    # rather than an obstacle: it is what proves `@task` returned the real signature.
    #
    # An annotated assignment still catches both regressions this file exists for. If `@task` went
    # back to erasing the type, `.body` would be `Unknown`, and reportAny — an error even in the
    # tests tier — fires on it. If it returned some other concrete callable, the declaration is a
    # type error.
    type_check_body: Callable[[Context], None] = quality.type_check.body
    audit_body: Callable[[Context], None] = deps.audit.body
    assert type_check_body is quality.type_check.body
    assert audit_body is deps.audit.body


def test_shipped_namespace_is_a_collection():
    # `from repo_tasks import ns` is the one import every consumer's tasks.py makes.
    assert_type(ns, Collection)


def test_task_bodies_are_callable_at_runtime_too():
    # A cheap runtime sanity check that `.body` is the undecorated function, which is what the
    # assert_type calls above claim statically.
    assert callable(quality.type_check.body)
    assert callable(deps.audit.body)

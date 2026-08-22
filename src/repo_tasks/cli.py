"""Standalone `repo-tasks` console script. Exists first to satisfy a real `uv tool install`
constraint: `--with-executables-from` only adds *extra* executables from a named dependency
(invoke's `inv`/`invoke`) on top of what's already there — it never substitutes for the primary
package providing at least one of its own. Without this, `uv tool install --with-executables-from
invoke repo-tasks` fails outright ("No executables are provided by package `repo-tasks`"),
confirmed against the real package, not just a sandboxed fixture.

Second, and just as load-bearing: bare `inv <task>` needs a `tasks.py`/`tasks/` somewhere in the
current directory or an ancestor to know what collection to load at all — there's no way to point
it at an arbitrary installed package's submodule (`inv -c repo_tasks.configs` doesn't work,
confirmed live). That makes `inv configs.ensure-deps` unreachable in the one case it exists for
(a repo with *nothing* invoke-related yet, not even a `tasks.py`) unless this standalone script
also exposes it directly — so `configs` is nested here too (`repo-tasks configs.ensure-deps`),
mirroring how it's nested under the main `repo_tasks.ns` collection.

Reuses selfinstall.py's/configs.py's tasks directly (no duplicated logic) — `repo-tasks
update`/`status`/`version`/`stamp`/`configs.ensure-deps`/`configs.pull`/`configs.diff` all work
standalone, independent of `inv` being on PATH or any local `tasks.py` existing at all."""

from importlib.metadata import version as _pkg_version

from invoke import Collection, Program

from . import configs, selfinstall

_namespace = Collection.from_module(selfinstall)
_namespace.add_collection(Collection.from_module(configs), name="configs")

program = Program(
    name="repo-tasks",
    binary="repo-tasks",
    version=_pkg_version("repo-tasks"),
    namespace=_namespace,
)

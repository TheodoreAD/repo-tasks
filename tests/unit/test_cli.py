"""Tests for repo_tasks.cli: the standalone `repo-tasks` console script's namespace.

Module-level wiring rather than task bodies — cli.py builds one Program and reuses selfinstall's and
configs' tasks verbatim, so what can regress here is which names the standalone binary exposes. Both
of the module's reasons for existing are load-bearing and neither is visible from `inv`: the console
script has to provide at least one executable of its own for `uv tool install
--with-executables-from` to work at all, and `configs.ensure-deps` has to be reachable in a repo
with no tasks.py for `inv` to find.
"""

from typing import cast

from invoke import Collection

from repo_tasks import cli


def test_program_is_named_for_the_console_script():
    # `[project.scripts]` maps `repo-tasks` at this Program; a mismatch would make every usage and
    # error message name a binary that does not exist.
    assert cli.program.name == "repo-tasks"
    assert cli.program.binary == "repo-tasks"


def test_program_reports_the_installed_version():
    # Read from package metadata, so `repo-tasks --version` cannot drift from what is installed.
    assert cli.program.version


def test_selfinstall_tasks_are_exposed_unprefixed():
    # These are what a machine with no local tasks.py runs, so they stay at the top level.
    assert {"update", "status", "version", "stamp"} <= set(cli._namespace.task_names)


def test_configs_is_nested_so_ensure_deps_is_reachable():
    # The one case configs.ensure-deps exists for is a repo with nothing invoke-related yet — no
    # tasks.py for `inv` to discover, and `inv -c repo_tasks.configs` does not work. If this
    # collection stops being nested here, that path has no entry point at all.
    assert "configs" in cli._namespace.collections
    # Cast for the same reason tasks.py casts here: invoke types Collection.collections loosely.
    nested = cast(Collection, cli._namespace.collections["configs"])
    # `ensure-deps`, not `ensure_deps`: invoke publishes the dashed CLI name here.
    assert {"ensure-deps", "pull", "diff"} <= set(nested.task_names)

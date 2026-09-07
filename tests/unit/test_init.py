"""Tests for repo_tasks's root `ns` — the ready-made Collection every consumer repo's tasks.py
imports directly, with each shipped module nested under its own name."""

from typing import cast

import pytest
from invoke import Collection

from repo_tasks import (
    agents,
    configs,
    configure,
    deps,
    dev_env,
    direnv,
    dist,
    docker,
    docs,
    helm,
    ns,
    quality,
    runner,
    selfinstall,
)
from repo_tasks import venv as venv_module


def test_ns_nests_quality_under_its_own_name():
    quality_collection = cast(Collection, ns.collections["quality"])
    assert quality_collection.task_names


def test_ns_quality_collection_contains_precommit():
    quality_collection = cast(Collection, ns.collections["quality"])
    assert "precommit" in quality_collection.task_names


def test_quality_module_is_individually_importable():
    assert quality.precommit is not None


def test_ns_configures_a_runner_only_when_report_mode_is_on():
    """The property the whole design rests on: without `REPO_TASKS_RUN_REPORT`, this package does
    not touch invoke's config at all, so `inv` behaves exactly as invoke documents.

    Asserted as a biconditional against the collection built at import, rather than as a flat "no
    runners key". The suite has to pass under both — `REPO_TASKS_RUN_REPORT=1 inv quality.check`
    runs this very file with the variable set, and a one-sided assertion fails there for a reason
    that has nothing to do with the code."""
    assert ("runners" in ns.configuration()) is runner.enabled()


def test_ns_installs_the_reporting_runner_when_report_mode_is_on(monkeypatch: pytest.MonkeyPatch):
    """The install is one `runner.configure` call at the end of `__init__.py`, so re-running it
    against a fresh collection is the honest way to exercise it without reimporting the package —
    and since it became a call rather than an inline `if`, this runs the shipped code instead of a
    copy of it that could drift."""
    monkeypatch.setenv("REPO_TASKS_RUN_REPORT", "1")
    collection = Collection()
    assert runner.configure(collection) is True
    assert collection.configuration()["runners"]["local"] is runner.ReportingLocal


def test_ns_nests_dev_env_under_its_own_name():
    # invoke dashifies the collection name for the CLI (`inv dev-env.setup`), same as it does for
    # underscored task names (`wire_claude_hook` -> `wire-claude-hook`) — the dict key reflects that.
    dev_env_collection = cast(Collection, ns.collections["dev-env"])
    assert "setup" in dev_env_collection.task_names


def test_ns_nests_docs_under_its_own_name():
    docs_collection = cast(Collection, ns.collections["docs"])
    assert {"clean", "build", "serve"} <= set(docs_collection.task_names)


def test_dev_env_module_is_individually_importable():
    assert dev_env.setup is not None


def test_docs_module_is_individually_importable():
    assert docs.build is not None


def test_ns_nests_venv_under_its_own_name():
    venv_collection = cast(Collection, ns.collections["venv"])
    assert {"sync", "create", "delete", "install-wheel"} <= set(venv_collection.task_names)


def test_ns_nests_ci_under_its_own_name():
    ci_collection = cast(Collection, ns.collections["ci"])
    assert "status" in set(ci_collection.task_names)


def test_ns_nests_deps_under_its_own_name():
    deps_collection = cast(Collection, ns.collections["deps"])
    assert {"lock", "check", "audit", "list", "tree", "export"} <= set(deps_collection.task_names)


def test_venv_module_is_individually_importable():
    assert venv_module.sync is not None


def test_deps_module_is_individually_importable():
    assert deps.lock is not None


def test_ns_nests_direnv_under_its_own_name():
    direnv_collection = cast(Collection, ns.collections["direnv"])
    assert "allow" in direnv_collection.task_names


def test_ns_nests_agents_under_its_own_name():
    agents_collection = cast(Collection, ns.collections["agents"])
    assert "wire-claude-hook" in agents_collection.task_names


def test_direnv_module_is_individually_importable():
    assert direnv.allow is not None


def test_agents_module_is_individually_importable():
    assert agents.wire_claude_hook is not None


def test_ns_nests_dist_under_its_own_name():
    dist_collection = cast(Collection, ns.collections["dist"])
    assert {"clean", "build", "publish", "list-versions"} <= set(dist_collection.task_names)


def test_dist_module_is_individually_importable():
    assert dist.build is not None


def test_ns_nests_docker_under_its_own_name():
    docker_collection = cast(Collection, ns.collections["docker"])
    assert {"build", "push", "release"} <= set(docker_collection.task_names)


def test_docker_module_is_individually_importable():
    assert docker.build is not None


def test_ns_nests_helm_under_its_own_name():
    helm_collection = cast(Collection, ns.collections["helm"])
    assert {"lint", "package", "push"} <= set(helm_collection.task_names)


def test_helm_module_is_individually_importable():
    assert helm.lint is not None


def test_ns_nests_configs_under_its_own_name():
    configs_collection = cast(Collection, ns.collections["configs"])
    assert {"pull", "diff"} <= set(configs_collection.task_names)


def test_configs_module_is_individually_importable():
    assert configs.pull is not None


def test_ns_has_configure_unnested_at_the_top_level():
    # Not a collection — the one command anything outside this package should ever need to
    # depend on by name (see configure.py), so it's a bare top-level task, same as
    # power-user-linux-setup's own `inv setup`.
    assert "configure" in ns.task_names


def test_configure_module_is_individually_importable():
    assert configure.configure is not None


def test_ns_nests_selfinstall_under_repo_tasks_name():
    # invoke dashifies the collection name for the CLI (`inv repo-tasks.update`) — nested
    # deliberately so these names can never collide with a consuming project's own local tasks.
    repo_tasks_collection = cast(Collection, ns.collections["repo-tasks"])
    assert {"update", "status", "version", "stamp"} <= set(repo_tasks_collection.task_names)


def test_selfinstall_module_is_individually_importable():
    assert selfinstall.update is not None

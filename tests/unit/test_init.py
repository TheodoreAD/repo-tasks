"""Tests for repo_tasks's root `ns` — the ready-made Collection every consumer repo's tasks.py
imports directly, with each shipped module nested under its own name."""

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
    selfinstall,
)
from repo_tasks import venv as venv_module


def test_ns_nests_quality_under_its_own_name():
    quality_collection = ns.collections["quality"]
    assert quality_collection is not None
    assert quality_collection.task_names


def test_ns_quality_collection_contains_precommit():
    quality_collection = ns.collections["quality"]
    assert quality_collection is not None
    assert "precommit" in quality_collection.task_names


def test_quality_module_is_individually_importable():
    assert quality.precommit is not None


def test_ns_nests_dev_env_under_its_own_name():
    # invoke dashifies the collection name for the CLI (`inv dev-env.setup`), same as it does for
    # underscored task names (`wire_claude_hook` -> `wire-claude-hook`) — the dict key reflects that.
    dev_env_collection = ns.collections["dev-env"]
    assert dev_env_collection is not None
    assert "setup" in dev_env_collection.task_names


def test_ns_nests_docs_under_its_own_name():
    docs_collection = ns.collections["docs"]
    assert docs_collection is not None
    assert {"clean", "build", "serve"} <= set(docs_collection.task_names)


def test_dev_env_module_is_individually_importable():
    assert dev_env.setup is not None


def test_docs_module_is_individually_importable():
    assert docs.build is not None


def test_ns_nests_venv_under_its_own_name():
    venv_collection = ns.collections["venv"]
    assert venv_collection is not None
    assert {"sync", "create", "delete", "install-wheel"} <= set(venv_collection.task_names)


def test_ns_nests_ci_under_its_own_name():
    ci_collection = ns.collections["ci"]
    assert ci_collection is not None
    assert "status" in set(ci_collection.task_names)


def test_ns_nests_deps_under_its_own_name():
    deps_collection = ns.collections["deps"]
    assert deps_collection is not None
    assert {"lock", "check", "audit", "list", "tree", "export"} <= set(deps_collection.task_names)


def test_venv_module_is_individually_importable():
    assert venv_module.sync is not None


def test_deps_module_is_individually_importable():
    assert deps.lock is not None


def test_ns_nests_direnv_under_its_own_name():
    direnv_collection = ns.collections["direnv"]
    assert direnv_collection is not None
    assert "allow" in direnv_collection.task_names


def test_ns_nests_agents_under_its_own_name():
    agents_collection = ns.collections["agents"]
    assert agents_collection is not None
    assert "wire-claude-hook" in agents_collection.task_names


def test_direnv_module_is_individually_importable():
    assert direnv.allow is not None


def test_agents_module_is_individually_importable():
    assert agents.wire_claude_hook is not None


def test_ns_nests_dist_under_its_own_name():
    dist_collection = ns.collections["dist"]
    assert dist_collection is not None
    assert {"clean", "build", "publish", "list-versions"} <= set(dist_collection.task_names)


def test_dist_module_is_individually_importable():
    assert dist.build is not None


def test_ns_nests_docker_under_its_own_name():
    docker_collection = ns.collections["docker"]
    assert docker_collection is not None
    assert {"build", "push", "release"} <= set(docker_collection.task_names)


def test_docker_module_is_individually_importable():
    assert docker.build is not None


def test_ns_nests_helm_under_its_own_name():
    helm_collection = ns.collections["helm"]
    assert helm_collection is not None
    assert {"lint", "package", "push"} <= set(helm_collection.task_names)


def test_helm_module_is_individually_importable():
    assert helm.lint is not None


def test_ns_nests_configs_under_its_own_name():
    configs_collection = ns.collections["configs"]
    assert configs_collection is not None
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
    repo_tasks_collection = ns.collections["repo-tasks"]
    assert repo_tasks_collection is not None
    assert {"update", "status", "version", "stamp"} <= set(repo_tasks_collection.task_names)


def test_selfinstall_module_is_individually_importable():
    assert selfinstall.update is not None

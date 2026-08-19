"""Tests for repo_tasks's root `ns` — the ready-made Collection every consumer repo's tasks.py
imports directly, with each shipped module nested under its own name."""

from repo_tasks import deps, dev_env, docs, ns, quality
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
    # underscored task names (`claude_hook` -> `claude-hook`) — the dict key reflects that.
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


def test_ns_nests_deps_under_its_own_name():
    deps_collection = ns.collections["deps"]
    assert deps_collection is not None
    assert {"lock", "check", "list", "tree", "export"} <= set(deps_collection.task_names)


def test_venv_module_is_individually_importable():
    assert venv_module.sync is not None


def test_deps_module_is_individually_importable():
    assert deps.lock is not None

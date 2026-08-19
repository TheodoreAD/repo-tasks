"""Tests for repo_tasks's root `ns` — the ready-made Collection every consumer repo's tasks.py
imports directly, with each shipped module nested under its own name."""

from repo_tasks import dev_env, docs, ns, quality


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

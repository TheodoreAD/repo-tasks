"""Tests for repo_tasks's root `ns` — the ready-made Collection every consumer repo's tasks.py
imports directly, with each shipped module nested under its own name."""

from repo_tasks import ns, quality


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

"""Tests for repo_tasks.configs: real filesystem materialization/diff against tmp_path (the
installed-package source, exercised via the default no-source-override path) plus the
--source local: override, which is also what the two-primitive authoring workflow
(configs.pull --source local:<path>, then configs-promote) actually relies on."""

import pytest
from invoke import Exit, MockContext

from repo_tasks import configs


def test_pull_materializes_every_file_from_installed_package(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configs.pull.body(MockContext(), source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    for name in configs._CONFIG_FILES:  # pyright: ignore[reportPrivateUsage]
        assert (tmp_path / name).read_text() == (configs._source_dir(None) / name).read_text()  # pyright: ignore[reportPrivateUsage]


def test_pull_overwrites_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ruff.toml").write_text("stale content")
    configs.pull.body(MockContext(), source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert (tmp_path / "ruff.toml").read_text() != "stale content"


def test_pull_from_local_source(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name in configs._CONFIG_FILES:  # pyright: ignore[reportPrivateUsage]
        (source_dir / name).write_text(f"content for {name}")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    monkeypatch.chdir(dest_dir)
    configs.pull.body(MockContext(), source=f"local:{source_dir}")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    for name in configs._CONFIG_FILES:  # pyright: ignore[reportPrivateUsage]
        assert (dest_dir / name).read_text() == f"content for {name}"


def test_source_dir_rejects_unknown_prefix():
    with pytest.raises(ValueError, match=r"git:.*local:"):
        configs._source_dir("bogus:whatever")  # pyright: ignore[reportPrivateUsage]


def test_diff_reports_up_to_date_when_matching(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    configs.pull.body(MockContext(), source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    configs.diff.body(MockContext(), source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "up to date" in capsys.readouterr().out


def test_diff_exits_nonzero_and_prints_unified_diff_when_differing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ruff.toml").write_text("stale content\n")
    with pytest.raises(Exit) as exc_info:
        configs.diff.body(MockContext(), source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ruff.toml differs" in out
    assert "-stale content" in out


def test_diff_never_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(Exit):
        configs.diff.body(MockContext(), source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert list(tmp_path.iterdir()) == []

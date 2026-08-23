"""Tests for repo_tasks.configs: real filesystem materialization/diff against tmp_path (the
installed-package source, exercised via the default no-source-override path) plus the
--source local: override, which is also what the two-primitive authoring workflow
(configs.pull --source local:<path>, then configs-promote) actually relies on."""

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import configs


def test_pull_materializes_every_file_from_installed_package(c, tmp_cwd):
    configs.pull.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    # pyrightconfig.json's `include` gets filtered to what actually exists at the pull target
    # (see test_pull_filters_pyright_include_to_existing_paths below) — every other file is a
    # verbatim copy of the canonical source.
    for name in [n for n in configs._CONFIG_FILES if n != "pyrightconfig.json"]:  # pyright: ignore[reportPrivateUsage]
        assert (tmp_cwd / name).read_text() == (configs._source_dir(None) / name).read_text()  # pyright: ignore[reportPrivateUsage]


def test_pull_filters_pyright_include_to_existing_paths(c, tmp_cwd):
    # basedpyright hard-errors (exit 3) on an `include` entry that isn't a real path, unlike
    # `exclude`, which tolerates missing entries fine — this is the fix for that, confirmed live
    # against the actual installed basedpyright, not just this filtering logic in isolation.
    (tmp_cwd / "tests").mkdir()
    (tmp_cwd / "tests" / "test_something.py").write_text("")
    configs.pull.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    pyright_text = (tmp_cwd / "pyrightconfig.json").read_text()
    assert '"include": ["tests"]' in pyright_text
    for missing in ("src", "tasks", "tasks.py"):
        assert f'"{missing}"' not in pyright_text


def test_pull_overwrites_existing_file(c, tmp_cwd):
    (tmp_cwd / "ruff.toml").write_text("stale content")
    configs.pull.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert (tmp_cwd / "ruff.toml").read_text() != "stale content"


def test_pull_from_local_source(c, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name in configs._CONFIG_FILES:  # pyright: ignore[reportPrivateUsage]
        (source_dir / name).write_text(f"content for {name}")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    monkeypatch.chdir(dest_dir)
    configs.pull.body(c, source=f"local:{source_dir}")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    for name in configs._CONFIG_FILES:  # pyright: ignore[reportPrivateUsage]
        assert (dest_dir / name).read_text() == f"content for {name}"


def test_source_dir_rejects_unknown_prefix():
    with pytest.raises(ValueError, match=r"git:.*local:"):
        configs._source_dir("bogus:whatever")  # pyright: ignore[reportPrivateUsage]


def test_diff_reports_up_to_date_when_matching(c, tmp_cwd, capsys):
    configs.pull.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    configs.diff.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "up to date" in capsys.readouterr().out


def test_diff_exits_nonzero_and_prints_unified_diff_when_differing(c, tmp_cwd, capsys):
    (tmp_cwd / "ruff.toml").write_text("stale content\n")
    with pytest.raises(Exit) as exc_info:
        configs.diff.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ruff.toml differs" in out
    assert "-stale content" in out


def test_diff_never_writes(c, tmp_cwd):
    with pytest.raises(Exit):
        configs.diff.body(c, source=None)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert list(tmp_cwd.iterdir()) == []


def test_ensure_deps_creates_pyproject_when_missing(tmp_path, monkeypatch):
    project_dir = tmp_path / "some-repo"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    c = MockContext(run=Result(exited=1))  # no git remote (and no git repo at all)
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    text = (project_dir / "pyproject.toml").read_text()
    assert 'name = "some-repo"' in text
    assert "package = false" in text
    assert "[tool.uv.sources]" not in text
    for dep in configs._quality_deps():  # pyright: ignore[reportPrivateUsage]
        assert f'"{dep}"' in text
    assert '"repo-tasks"' not in text
    assert '"invoke"' not in text
    for name in configs._CONFIG_FILES:  # pyright: ignore[reportPrivateUsage]
        assert (project_dir / name).exists()  # quality.check needs these, not just the deps


def test_ensure_deps_creates_tasks_py_alongside_dummy_pyproject(tmp_cwd):
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "from repo_tasks import ns" in (tmp_cwd / "tasks.py").read_text()


def test_ensure_deps_does_not_overwrite_existing_tasks_py(tmp_cwd):
    (tmp_cwd / "tasks.py").write_text("# hand-written\n")
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert (tmp_cwd / "tasks.py").read_text() == "# hand-written\n"


def test_ensure_deps_derives_name_from_git_remote(tmp_cwd):
    c = MockContext(run=Result(stdout="git@github.com:someone/my-project.git\n", exited=0))
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert 'name = "my-project"' in (tmp_cwd / "pyproject.toml").read_text()


def test_ensure_deps_adds_missing_and_leaves_present_entries_untouched(tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n\n'
        "[dependency-groups]\n"
        'dev = [\n  "ruff>=0.0.1",\n  "repo-tasks",\n  "invoke",\n]\n'
    )
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    text = (tmp_cwd / "pyproject.toml").read_text()
    assert '"ruff>=0.0.1"' in text  # untouched, not reversioned to the canonical ruff spec
    assert text.count('"repo-tasks"') == 1  # untouched, never duplicated or removed
    assert text.count('"invoke"') == 1
    for dep in configs._quality_deps():  # pyright: ignore[reportPrivateUsage]
        if configs._bare_name(dep) != "ruff":  # pyright: ignore[reportPrivateUsage]
            assert f'"{dep}"' in text


def test_ensure_deps_idempotent_on_second_run(tmp_cwd):
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    first = (tmp_cwd / "pyproject.toml").read_text()
    configs.ensure_deps.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert (tmp_cwd / "pyproject.toml").read_text() == first

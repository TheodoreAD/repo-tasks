"""Tests for repo_tasks.configs: real filesystem materialization/diff against tmp_path (the
installed-package source, exercised via the default no-source-override path) plus the
--source local: override, which is also what the two-primitive authoring workflow
(configs.pull --source local:<path>, then configs-promote) actually relies on."""

import re

import pytest
from invoke.context import MockContext
from invoke.exceptions import Exit
from invoke.runners import Result

from repo_tasks import configs


def test_pull_materializes_every_file_verbatim_from_installed_package(c, tmp_cwd):
    configs.pull.body(c, source=None)
    # Verbatim, pyrightconfig.json included: its `include` used to be filtered per consumer to
    # the entries that existed (a literal path that doesn't exist is a hard basedpyright error),
    # which made root and package diverge and let `configs.promote` ship the narrowed list back
    # as canonical. The shipped globs tolerate absence, so nothing is resolved any more.
    for name in configs._CONFIG_FILES:
        assert (tmp_cwd / name).read_text() == (configs._source_dir(None) / name).read_text()


def test_shipped_pyright_include_entries_tolerate_absence():
    # Every entry must be a glob in its last segment — `tests*`, not `tests` or `tests/**`: only
    # that shape exits 0 when nothing matches (measured against basedpyright 1.39.10), and it is
    # the entire reason pull can be verbatim. A literal entry would exit 3 in any consumer that
    # lacks the path.
    text = (configs._source_dir(None) / "pyrightconfig.json").read_text()
    entries: list[str] = re.findall(r'"([^"]+)"', re.search(r'"include":\s*\[([^\]]*)\]', text).group(1))  # pyright: ignore[reportOptionalMemberAccess]
    assert entries
    for entry in entries:
        assert entry.endswith("*") and "/" not in entry, entry


def test_pull_overwrites_existing_file(c, tmp_cwd):
    (tmp_cwd / "ruff.toml").write_text("stale content")
    configs.pull.body(c, source=None)
    assert (tmp_cwd / "ruff.toml").read_text() != "stale content"


def test_pull_from_local_source(c, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name in configs._CONFIG_FILES:
        (source_dir / name).write_text(f"content for {name}")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    monkeypatch.chdir(dest_dir)
    configs.pull.body(c, source=f"local:{source_dir}")
    for name in configs._CONFIG_FILES:
        assert (dest_dir / name).read_text() == f"content for {name}"


def test_source_dir_rejects_unknown_prefix():
    with pytest.raises(ValueError, match=r"git:.*local:"):
        configs._source_dir("bogus:whatever")


def test_diff_reports_up_to_date_when_matching(c, tmp_cwd, capsys):
    configs.pull.body(c, source=None)
    configs.diff.body(c, source=None)
    assert "up to date" in capsys.readouterr().out


def test_diff_exits_nonzero_and_prints_unified_diff_when_differing(c, tmp_cwd, capsys):
    (tmp_cwd / "ruff.toml").write_text("stale content\n")
    with pytest.raises(Exit) as exc_info:
        configs.diff.body(c, source=None)
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ruff.toml differs" in out
    assert "-stale content" in out


def test_diff_never_writes(c, tmp_cwd):
    with pytest.raises(Exit):
        configs.diff.body(c, source=None)
    assert list(tmp_cwd.iterdir()) == []


def test_ensure_deps_creates_pyproject_when_missing(tmp_path, monkeypatch):
    project_dir = tmp_path / "some-repo"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    c = MockContext(run=Result(exited=1))  # no git remote (and no git repo at all)
    configs.ensure_deps.body(c)
    text = (project_dir / "pyproject.toml").read_text()
    assert 'name = "some-repo"' in text
    assert "package = false" in text
    assert "[tool.uv.sources]" not in text
    for dep in configs._quality_deps():
        assert f'"{dep}"' in text
    assert '"repo-tasks"' not in text
    assert '"invoke"' not in text
    for name in configs._CONFIG_FILES:
        assert (project_dir / name).exists()  # quality.check needs these, not just the deps


def test_ensure_deps_creates_tasks_py_alongside_dummy_pyproject(tmp_cwd):
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    assert "from repo_tasks import ns" in (tmp_cwd / "tasks.py").read_text()


def test_ensure_deps_does_not_overwrite_existing_tasks_py(tmp_cwd):
    (tmp_cwd / "tasks.py").write_text("# hand-written\n")
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    assert (tmp_cwd / "tasks.py").read_text() == "# hand-written\n"


def test_ensure_deps_derives_name_from_git_remote(tmp_cwd):
    c = MockContext(run=Result(stdout="git@github.com:someone/my-project.git\n", exited=0))
    configs.ensure_deps.body(c)
    assert 'name = "my-project"' in (tmp_cwd / "pyproject.toml").read_text()


def test_ensure_deps_adds_missing_and_leaves_present_entries_untouched(tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n\n'
        "[dependency-groups]\n"
        'dev = [\n  "ruff>=0.0.1",\n  "repo-tasks",\n  "invoke",\n]\n'
    )
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    text = (tmp_cwd / "pyproject.toml").read_text()
    assert '"ruff>=0.0.1"' in text  # untouched, not reversioned to the canonical ruff spec
    assert text.count('"repo-tasks"') == 1  # untouched, never duplicated or removed
    assert text.count('"invoke"') == 1
    for dep in configs._quality_deps():
        if configs._bare_name(dep) != "ruff":
            assert f'"{dep}"' in text


@pytest.mark.parametrize("empty_array", ["dev = []", "dev = [\n]"])
def test_ensure_deps_rebuilds_an_empty_dev_array_in_multiline_shape(tmp_cwd, empty_array):
    # Splicing after the opening bracket of `dev = []` used to leave the first entry on the
    # bracket's line — a shape dprint rejects, and this runs before any venv (so any dprint)
    # exists. Both empty spellings must come out as the one multi-line shape dprint accepts.
    head = '[project]\nname = "x"\nversion = "0.1.0"\n\n[dependency-groups]\n'
    (tmp_cwd / "pyproject.toml").write_text(f"{head}{empty_array}\n")
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    expected = "dev = [\n" + "".join(f'  "{dep}",\n' for dep in configs._quality_deps()) + "]\n"
    assert (tmp_cwd / "pyproject.toml").read_text().endswith(f"[dependency-groups]\n{expected}")


def test_ensure_deps_idempotent_on_second_run(tmp_cwd):
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    first = (tmp_cwd / "pyproject.toml").read_text()
    configs.ensure_deps.body(c)
    assert (tmp_cwd / "pyproject.toml").read_text() == first

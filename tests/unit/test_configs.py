"""Tests for repo_tasks.configs: real filesystem materialization/diff against tmp_path (the
installed-package source, exercised via the default no-source-override path) plus the
--source local: override, which is also what the two-primitive authoring workflow
(configs.pull --source local:<path>, then configs-promote) actually relies on."""

import re
import shutil
from pathlib import Path

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import configs

_MINIMAL_PYPROJECT = '[project]\nname = "x"\nversion = "0.1.0"\n\n[dependency-groups]\n'


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
        # Split, not one composite assertion: the two halves fail for different reasons — a literal
        # entry (exit 3 where the path is absent) versus a nested one (the glob stops anchoring) —
        # and a combined assert reports neither.
        assert entry.endswith("*"), entry
        assert "/" not in entry, entry


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


def _write_up_to_date_dev_group(tmp_cwd):
    """A pyproject declaring the whole canonical manifest, so `diff`'s dev-group half is clean and
    a test can isolate the config-file half."""
    deps = "".join(f'  "{dep}",\n' for dep in configs._quality_deps())
    (tmp_cwd / "pyproject.toml").write_text(f"{_MINIMAL_PYPROJECT}dev = [\n{deps}]\n")


def test_diff_reports_up_to_date_when_matching(c, tmp_cwd, capsys):
    configs.pull.body(c, source=None)
    _write_up_to_date_dev_group(tmp_cwd)
    configs.diff.body(c, source=None)
    assert "up to date" in capsys.readouterr().out


def test_diff_exits_nonzero_and_prints_unified_diff_when_differing(c, tmp_cwd, capsys):
    _write_up_to_date_dev_group(tmp_cwd)
    (tmp_cwd / "ruff.toml").write_text("stale content\n")
    with pytest.raises(Exit) as exc_info:
        configs.diff.body(c, source=None)
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "ruff.toml differs" in out
    assert "-stale content" in out
    assert "inv configs.pull" in out  # the fix, not just the finding


def test_diff_never_writes(c, tmp_cwd):
    with pytest.raises(Exit):
        configs.diff.body(c, source=None)
    assert list(tmp_cwd.iterdir()) == []


def test_diff_reports_dev_group_drift_with_configs_already_up_to_date(c, tmp_cwd, capsys):
    # The incident shape: every shipped config file matches, and the only drift is an entry the
    # manifest grew after this consumer was bootstrapped. Without this half, `diff` says "up to
    # date" and the gate still dies on exit 127.
    configs.pull.body(c, source=None)
    kept = [d for d in configs._quality_deps() if configs._bare_name(d) != "actionlint-py"]
    deps = "".join(f'  "{dep}",\n' for dep in kept)
    (tmp_cwd / "pyproject.toml").write_text(f"{_MINIMAL_PYPROJECT}dev = [\n{deps}]\n")
    with pytest.raises(Exit) as exc_info:
        configs.diff.body(c, source=None)
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "dependency-groups.dev is missing: actionlint-py" in out
    assert "configs.ensure-deps" in out
    assert "inv configs.pull" not in out  # config files matched — don't hand out an unrelated fix


def test_declared_dev_names_follows_include_group(tmp_cwd):
    # repo-tasks' own shape: dev reaches the manifest through an include-group, never by listing
    # the entries. A check that missed this would report the whole manifest missing in this repo.
    (tmp_cwd / "pyproject.toml").write_text(
        f'{_MINIMAL_PYPROJECT}repo-tasks-quality = [\n  "ruff",\n]\n'
        'dev = [\n  { include-group = "repo-tasks-quality" },\n  "pytest",\n]\n'
    )
    assert configs._declared_dev_names(tmp_cwd / "pyproject.toml") == {"ruff", "pytest"}


def test_declared_dev_names_survives_a_cyclic_include_group(tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text(
        f'{_MINIMAL_PYPROJECT}dev = [\n  {{ include-group = "other" }},\n]\n'
        'other = [\n  { include-group = "dev" },\n  "ruff",\n]\n'
    )
    assert configs._declared_dev_names(tmp_cwd / "pyproject.toml") == {"ruff"}


def test_this_repos_own_dev_group_satisfies_the_manifest_it_publishes():
    # Dogfooding, asserted rather than assumed: repo-tasks reaches its own manifest through an
    # include-group, and if that ever stopped resolving, `inv configs.diff` here would report drift
    # against itself. Read-only and by path, so the tier's no-chdir-outside-tmp_path contract holds.
    own = Path(__file__).parent.parent.parent / "pyproject.toml"
    assert {configs._bare_name(dep) for dep in configs._quality_deps()} <= configs._declared_dev_names(own)


def test_missing_quality_deps_reports_everything_when_there_is_no_pyproject(tmp_cwd):
    assert configs._missing_quality_deps() == [configs._bare_name(d) for d in configs._quality_deps()]


def test_every_gate_tool_maps_to_a_real_manifest_entry():
    # The mapping is hand-written (four of the seven distributions are named differently from the
    # binary they install), so a manifest rename would otherwise leave `require_tool` naming a
    # package that no longer exists — precisely when the message matters most.
    manifest = {configs._bare_name(dep) for dep in configs._quality_deps()}
    for tool, distribution in configs._GATE_TOOL_DISTRIBUTIONS.items():
        assert distribution in manifest, tool


def test_require_tool_returns_silently_when_the_binary_is_present(monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    configs.require_tool("actionlint")
    assert capsys.readouterr().out == ""


def test_require_tool_exits_naming_the_distribution_and_the_fix(monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(Exit) as exc_info:
        configs.require_tool("shfmt")
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "shfmt not found on PATH" in out
    assert "shfmt-py" in out  # the entry to add, which the binary name does not give you
    assert "configs.ensure-deps" in out
    assert "inv deps.lock" in out


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

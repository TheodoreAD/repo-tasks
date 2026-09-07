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


def test_pull_materializes_every_underived_file_verbatim_from_installed_package(c, tmp_cwd):
    configs.pull.body(c, source=None)
    # Verbatim for everything `_derive_for_project` does not touch, pyrightconfig.json's `include`
    # among it: that used to be filtered per consumer to the entries that existed (a literal path
    # that doesn't exist is a hard basedpyright error), which made root and package diverge and let
    # `configs.promote` ship the narrowed list back as canonical. The shipped globs tolerate
    # absence, so nothing about `include` is resolved any more.
    for name in configs._CONFIG_FILES:
        pulled = (tmp_cwd / name).read_text(encoding="utf-8")
        canonical = (configs._source_dir(None) / name).read_text(encoding="utf-8")
        assert pulled == configs._derive_for_project(name, canonical, tmp_cwd)
        if name not in {"pyrightconfig.json", "pytest.ini"}:
            assert pulled == canonical


def test_pull_derives_python_version_from_the_consumers_requires_python(c, tmp_cwd, write_pyproject):
    write_pyproject(tmp_cwd, version=None, requires_python=">=3.13")
    configs.pull.body(c, source=None)
    assert '"pythonVersion": "3.13",' in (tmp_cwd / "pyrightconfig.json").read_text(encoding="utf-8")


def test_pull_omits_python_version_entirely_when_the_consumer_declares_no_floor(c, tmp_cwd, write_pyproject):
    # Not "fall back to repo-tasks' own floor": that is the failure the shipped ruff.toml's
    # `target-version` pin was deleted for — a floor nobody in that project chose. With the key
    # absent basedpyright infers the interpreter it finds, which is what it did before this
    # derivation existed, and a package with no `requires-python` is broken independently of us.
    write_pyproject(tmp_cwd, version=None)
    configs.pull.body(c, source=None)
    text = (tmp_cwd / "pyrightconfig.json").read_text(encoding="utf-8")
    assert "pythonVersion" not in text
    # The removal must not strand a comma or leave the JSON otherwise unparseable.
    assert '"typeCheckingMode": "recommended",\n' in text


def test_pull_emits_anyio_mode_only_when_the_consumers_lock_resolves_anyio(c, tmp_cwd):
    (tmp_cwd / "uv.lock").write_text('[[package]]\nname = "anyio"\nversion = "4.14.2"\n', encoding="utf-8")
    configs.pull.body(c, source=None)
    assert "anyio_mode = auto" in (tmp_cwd / "pytest.ini").read_text(encoding="utf-8")


def test_pull_drops_anyio_mode_when_the_consumer_has_no_lock(c, tmp_cwd):
    # The shipped `addopts` carries --strict-config, so an unrecognised key is exit 4 with no test
    # executed rather than a warning — this is the branch that keeps a global-uv-tool consumer's
    # suite runnable at all.
    configs.pull.body(c, source=None)
    text = (tmp_cwd / "pytest.ini").read_text(encoding="utf-8")
    assert "anyio_mode" not in text
    assert "addopts = -ra --strict-markers --strict-config\n" in text


def test_project_resolves_anyio_is_not_fooled_by_a_prefixed_package_name(tmp_cwd):
    (tmp_cwd / "uv.lock").write_text('[[package]]\nname = "anyio-extras"\nversion = "1.0"\n', encoding="utf-8")
    assert configs._project_resolves_anyio(tmp_cwd) is False


def test_restore_derived_lines_keeps_the_packages_own_python_version():
    # The promote guard. A root copy pulled in a repo whose floor is 3.13 must not carry that 3.13
    # back into the packaged placeholder every consumer then derives from.
    package = '{\n  "pythonVersion": "3.11",\n  "reportAny": "error"\n}\n'
    root = '{\n  "pythonVersion": "3.13",\n  "reportAny": "warning"\n}\n'
    restored = configs.restore_derived_lines(root, package)
    assert restored == '{\n  "pythonVersion": "3.11",\n  "reportAny": "warning"\n}\n'


def test_restore_derived_lines_refuses_when_one_side_lacks_the_line_entirely():
    # Presence differing means the promoting repo declares no floor while the package does; nothing
    # here knows where in the file the missing line belongs, so the caller has to refuse.
    root = '{\n  "reportAny": "error"\n}\n'
    package = '{\n  "pythonVersion": "3.11",\n  "reportAny": "error"\n}\n'
    assert configs.restore_derived_lines(root, package) is None


def test_restore_derived_lines_leaves_an_underived_file_untouched():
    text = "line-length = 120\n"
    assert configs.restore_derived_lines(text, "line-length = 100\n") == text


def test_shipped_pyright_include_entries_tolerate_absence():
    # Every entry must be a glob in its last segment — `tests*`, not `tests` or `tests/**`: only
    # that shape exits 0 when nothing matches (measured against basedpyright 1.39.10), and it is
    # the entire reason pull can be verbatim. A literal entry would exit 3 in any consumer that
    # lacks the path.
    text = (configs._source_dir(None) / "pyrightconfig.json").read_text(encoding="utf-8")
    entries: list[str] = re.findall(r'"([^"]+)"', re.search(r'"include":\s*\[([^\]]*)\]', text).group(1))  # pyright: ignore[reportOptionalMemberAccess]
    assert entries
    for entry in entries:
        # Split, not one composite assertion: the two halves fail for different reasons — a literal
        # entry (exit 3 where the path is absent) versus a nested one (the glob stops anchoring) —
        # and a combined assert reports neither.
        assert entry.endswith("*"), entry
        assert "/" not in entry, entry


def test_pull_overwrites_existing_file(c, tmp_cwd):
    (tmp_cwd / "ruff.toml").write_text("stale content", encoding="utf-8")
    configs.pull.body(c, source=None)
    assert (tmp_cwd / "ruff.toml").read_text(encoding="utf-8") != "stale content"


def test_pull_from_local_source(c, tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name in configs._CONFIG_FILES:
        (source_dir / name).write_text(f"content for {name}", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    monkeypatch.chdir(dest_dir)
    configs.pull.body(c, source=f"local:{source_dir}")
    for name in configs._CONFIG_FILES:
        assert (dest_dir / name).read_text(encoding="utf-8") == f"content for {name}"


def test_source_dir_rejects_unknown_prefix():
    with pytest.raises(ValueError, match=r"git:.*local:"):
        configs._source_dir("bogus:whatever")


def _write_up_to_date_dev_group(tmp_cwd):
    """A pyproject declaring the whole canonical manifest, so `diff`'s dev-group half is clean and
    a test can isolate the config-file half."""
    deps = "".join(f'  "{dep}",\n' for dep in configs._quality_deps())
    (tmp_cwd / "pyproject.toml").write_text(f"{_MINIMAL_PYPROJECT}dev = [\n{deps}]\n", encoding="utf-8")


def test_diff_reports_up_to_date_when_matching(c, tmp_cwd, capsys):
    configs.pull.body(c, source=None)
    _write_up_to_date_dev_group(tmp_cwd)
    configs.diff.body(c, source=None)
    assert "up to date" in capsys.readouterr().out


def test_diff_applies_the_same_derivation_so_a_derived_file_never_reports_drift(c, tmp_cwd, capsys):
    # The invariant the whole derivation rests on. `pull` writes a pyrightconfig.json and pytest.ini
    # that differ from the packaged copies by construction, so a `diff` comparing against those
    # copies would report drift forever and the next `pull` would "fix" nothing. Both declarations
    # are non-default here (3.13, and a lock with AnyIO) so the test fails if either side silently
    # falls back to the packaged text.
    deps = "".join(f'  "{dep}",\n' for dep in configs._quality_deps())
    (tmp_cwd / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "0.1.0"\nrequires-python = ">=3.13"\n\n'
        f"[dependency-groups]\ndev = [\n{deps}]\n",
        encoding="utf-8",
    )
    (tmp_cwd / "uv.lock").write_text('[[package]]\nname = "anyio"\nversion = "4.14.2"\n', encoding="utf-8")
    configs.pull.body(c, source=None)
    configs.diff.body(c, source=None)
    assert "up to date" in capsys.readouterr().out
    assert '"pythonVersion": "3.13",' in (tmp_cwd / "pyrightconfig.json").read_text(encoding="utf-8")
    assert "anyio_mode = auto" in (tmp_cwd / "pytest.ini").read_text(encoding="utf-8")


def test_diff_exits_nonzero_and_prints_unified_diff_when_differing(c, tmp_cwd, capsys):
    _write_up_to_date_dev_group(tmp_cwd)
    (tmp_cwd / "ruff.toml").write_text("stale content\n", encoding="utf-8")
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
    (tmp_cwd / "pyproject.toml").write_text(f"{_MINIMAL_PYPROJECT}dev = [\n{deps}]\n", encoding="utf-8")
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
        'dev = [\n  { include-group = "repo-tasks-quality" },\n  "pytest",\n]\n',
        encoding="utf-8",
    )
    assert configs._declared_dev_names(tmp_cwd / "pyproject.toml") == {"ruff", "pytest"}


def test_declared_dev_names_survives_a_cyclic_include_group(tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text(
        f'{_MINIMAL_PYPROJECT}dev = [\n  {{ include-group = "other" }},\n]\n'
        'other = [\n  { include-group = "dev" },\n  "ruff",\n]\n',
        encoding="utf-8",
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


def test_require_tool_warns_when_the_binary_is_present_but_undeclared(monkeypatch, capsys):
    """The masking the warning exists for: on a workstation with the tool installed user-wide,
    `which` finds it, the preflight cannot fire, and the gate passes here while CI — which has only
    the project's own environment — fails. Measured on the dev machine 2026-09-06: four of the eight
    gate binaries resolved from ~/.local/bin with the venv off PATH."""
    monkeypatch.setattr(shutil, "which", lambda name: f"/home/dev/.local/bin/{name}")
    monkeypatch.setattr(configs, "_missing_quality_deps", lambda: ["actionlint-py"])
    configs.require_tool("actionlint")  # a warning, never a raise — see _warn_if_undeclared
    out = capsys.readouterr().out
    assert "/home/dev/.local/bin/actionlint" in out, "name where it actually resolved from"
    assert "actionlint-py" in out, "the entry to add, which the binary name does not give you"
    assert "fail in CI" in out
    assert "configs.ensure-deps" in out


def test_require_tool_warns_against_a_real_stale_pyproject(tmp_path, monkeypatch, capsys):
    """The same path with nothing about the drift stubbed — a real consumer pyproject whose dev
    group predates the manifest entry, read by the real `_missing_quality_deps`. The stubbed test
    above proves the message; this one proves the two halves are actually wired together."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "stale-consumer"\nversion = "0.1.0"\n\n[dependency-groups]\ndev = ["ruff"]\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: f"/home/dev/.local/bin/{name}")
    configs.require_tool("actionlint")
    assert "actionlint-py" in capsys.readouterr().out


def test_require_tool_stays_silent_when_the_binary_is_present_and_declared(monkeypatch, capsys):
    """The ordinary case, pinned explicitly rather than relying on this repo's own pyproject being
    complete — which is what makes the silence above meaningful."""
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(configs, "_missing_quality_deps", list)
    configs.require_tool("actionlint")
    assert capsys.readouterr().out == ""


def test_ensure_deps_creates_pyproject_when_missing(tmp_path, monkeypatch):
    project_dir = tmp_path / "some-repo"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    c = MockContext(run=Result(exited=1))  # no git remote (and no git repo at all)
    configs.ensure_deps.body(c)
    text = (project_dir / "pyproject.toml").read_text(encoding="utf-8")
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
    assert "from repo_tasks import ns" in (tmp_cwd / "tasks.py").read_text(encoding="utf-8")


def test_ensure_deps_does_not_overwrite_existing_tasks_py(tmp_cwd):
    (tmp_cwd / "tasks.py").write_text("# hand-written\n", encoding="utf-8")
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    assert (tmp_cwd / "tasks.py").read_text(encoding="utf-8") == "# hand-written\n"


def test_ensure_deps_derives_name_from_git_remote(tmp_cwd):
    c = MockContext(run=Result(stdout="git@github.com:someone/my-project.git\n", exited=0))
    configs.ensure_deps.body(c)
    assert 'name = "my-project"' in (tmp_cwd / "pyproject.toml").read_text(encoding="utf-8")


def test_ensure_deps_adds_missing_and_leaves_present_entries_untouched(tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n\n'
        "[dependency-groups]\n"
        'dev = [\n  "ruff>=0.0.1",\n  "repo-tasks",\n  "invoke",\n]\n',
        encoding="utf-8",
    )
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    text = (tmp_cwd / "pyproject.toml").read_text(encoding="utf-8")
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
    (tmp_cwd / "pyproject.toml").write_text(f"{head}{empty_array}\n", encoding="utf-8")
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    expected = "dev = [\n" + "".join(f'  "{dep}",\n' for dep in configs._quality_deps()) + "]\n"
    assert (tmp_cwd / "pyproject.toml").read_text(encoding="utf-8").endswith(f"[dependency-groups]\n{expected}")


def test_ensure_deps_idempotent_on_second_run(tmp_cwd):
    c = MockContext(run=Result(exited=1))
    configs.ensure_deps.body(c)
    first = (tmp_cwd / "pyproject.toml").read_text(encoding="utf-8")
    configs.ensure_deps.body(c)
    assert (tmp_cwd / "pyproject.toml").read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# version-constraint drift (the half a bare-name comparison cannot see)
# ---------------------------------------------------------------------------


def _consumer_pyproject(tmp_path, dev_entries: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "c"\nversion = "0.1.0"\n\n[dependency-groups]\ndev = [{dev_entries}]\n', encoding="utf-8"
    )


def test_a_bare_name_does_not_carry_the_manifests_constraint(tmp_path, monkeypatch):
    """The finding this exists for, reproduced: `hadolint-py` gained `!=2.15.1.2` because that
    release's macOS wheel is a corrupt zip, and a consumer declaring a bare `hadolint-py` was
    reported up to date — so the fix reached nobody."""
    _consumer_pyproject(tmp_path, '"hadolint-py"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(configs, "_quality_deps", lambda: ["hadolint-py!=2.15.1.2"])
    assert configs._missing_quality_deps() == [], "the name is present — which is exactly the blind spot"
    assert configs._unconstrained_quality_deps() == ["hadolint-py!=2.15.1.2"]


def test_carrying_the_constraint_is_not_drift(tmp_path, monkeypatch):
    _consumer_pyproject(tmp_path, '"hadolint-py!=2.15.1.2"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(configs, "_quality_deps", lambda: ["hadolint-py!=2.15.1.2"])
    assert configs._unconstrained_quality_deps() == []


def test_a_consumer_may_pin_tighter_without_drifting_forever(tmp_path, monkeypatch):
    """Containment, not equality. A consumer that carries the manifest's clauses plus its own is
    doing nothing wrong, and a check that flagged it every run would be turned off."""
    _consumer_pyproject(tmp_path, '"hadolint-py>=2.14,!=2.15.1.2"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(configs, "_quality_deps", lambda: ["hadolint-py!=2.15.1.2"])
    assert configs._unconstrained_quality_deps() == []


def test_whitespace_in_a_retyped_entry_is_not_drift(tmp_path, monkeypatch):
    """The one difference a human retyping an entry actually introduces."""
    _consumer_pyproject(tmp_path, '"hadolint-py != 2.15.1.2"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(configs, "_quality_deps", lambda: ["hadolint-py!=2.15.1.2"])
    assert configs._unconstrained_quality_deps() == []


def test_an_unconstrained_manifest_entry_never_reports_drift(tmp_path, monkeypatch):
    """Most of the manifest carries no constraint at all, and those must stay a presence check —
    otherwise every consumer would report drift on every entry."""
    _consumer_pyproject(tmp_path, '"ruff"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(configs, "_quality_deps", lambda: ["ruff"])
    assert configs._unconstrained_quality_deps() == []


def test_a_package_not_declared_at_all_is_missing_not_unconstrained(tmp_path, monkeypatch):
    """The two findings must not double-report: an absent entry is `ensure-deps`' job, and saying
    it twice would send the reader to a hand edit that ensure-deps is about to make unnecessary."""
    _consumer_pyproject(tmp_path, '"ruff"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(configs, "_quality_deps", lambda: ["hadolint-py!=2.15.1.2"])
    assert configs._missing_quality_deps() == ["hadolint-py"]
    assert configs._unconstrained_quality_deps() == []


def test_version_clauses_ignores_extras_and_markers():
    assert configs._version_clauses("pkg") == frozenset()
    assert configs._version_clauses("pkg[extra]>=1.0") == frozenset({">=1.0"})
    assert configs._version_clauses('pkg>=1.0; python_version < "3.12"') == frozenset({">=1.0"})
    assert configs._version_clauses("pkg>=1.0,!=1.2") == frozenset({">=1.0", "!=1.2"})

"""Tests for repo_tasks.venv: asserts the exact command string each task builds via invoke's
MockContext, plus `delete`'s real filesystem exists-check/rmtree behavior against tmp_path."""

import pytest
from invoke import Exit, MockContext, Result

from repo_tasks import venv


def test_sync_default(c):
    venv.sync.body(c)
    c.run.assert_called_once_with("uv sync --locked", echo=True)


def test_sync_no_editable(c):
    venv.sync.body(c, no_editable=True)
    c.run.assert_called_once_with("uv sync --locked --no-editable", echo=True)


def test_sync_no_dev(c):
    venv.sync.body(c, no_dev=True)
    c.run.assert_called_once_with("uv sync --locked --no-dev", echo=True)


def test_sync_no_install_project(c):
    venv.sync.body(c, no_install_project=True)
    c.run.assert_called_once_with("uv sync --locked --no-install-project", echo=True)


def test_sync_project_narrows_to_one_workspace_member(c):
    venv.sync.body(c, project="sample-service")
    c.run.assert_called_once_with("uv sync --locked --package sample-service", echo=True)


def test_sync_all_flags_combined(c):
    venv.sync.body(c, no_editable=True, no_dev=True, no_install_project=True)
    c.run.assert_called_once_with("uv sync --locked --no-editable --no-dev --no-install-project", echo=True)


def test_delete_noop_when_venv_absent(c, tmp_cwd, capsys):
    venv.delete.body(c)
    assert "nothing to clean" in capsys.readouterr().out


def test_delete_removes_venv(c, tmp_cwd):
    (tmp_cwd / ".venv").mkdir()
    venv.delete.body(c)
    assert not (tmp_cwd / ".venv").exists()


def test_install_wheel_default(c):
    venv.install_wheel.body(c)
    c.run.assert_called_once_with("uv pip install --no-deps dist/*.whl", echo=True)


def test_install_wheel_explicit_path():
    c = MockContext(run=Result())
    venv.install_wheel.body(c, wheel="dist/repo_tasks-0.1.0-py3-none-any.whl")
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "uv pip install --no-deps dist/repo_tasks-0.1.0-py3-none-any.whl", echo=True
    )


def test_sync_does_not_touch_github_path_when_unset(c, tmp_cwd, monkeypatch):
    monkeypatch.delenv("GITHUB_PATH", raising=False)
    venv.sync.body(c)
    # No GITHUB_PATH file was ever created/written -- nothing to assert on disk beyond this not
    # raising, since there's no path to check.


def test_sync_registers_venv_bin_on_github_path_when_set(c, tmp_cwd, monkeypatch):
    github_path_file = tmp_cwd / "github_path"
    github_path_file.touch()
    monkeypatch.setenv("GITHUB_PATH", str(github_path_file))
    venv.sync.body(c)
    assert github_path_file.read_text() == f"{(tmp_cwd / '.venv' / 'bin').resolve()}\n"


def test_sync_python_names_the_interpreter(c):
    venv.sync.body(c, python="3.11")
    c.run.assert_called_once_with("uv sync --locked --python 3.11", echo=True)


def _declare(tmp_cwd, spec: str) -> None:
    (tmp_cwd / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "0.1.0"\nrequires-python = "{spec}"\n')


def _venv_on(tmp_cwd, version: str) -> None:
    (tmp_cwd / ".venv").mkdir(exist_ok=True)
    (tmp_cwd / ".venv" / "pyvenv.cfg").write_text(f"implementation = CPython\nversion_info = {version}\n")


def test_check_passes_when_the_venv_matches_the_declaration(c, tmp_cwd, capsys):
    _declare(tmp_cwd, ">=3.11")
    _venv_on(tmp_cwd, "3.11.15")
    venv.check.body(c)
    assert "as declared" in capsys.readouterr().out


def test_check_reports_and_exits_nonzero_on_a_mismatch(c, tmp_cwd, capsys):
    # The silent state this task exists for: uv builds with the newest interpreter satisfying the
    # floor, so a repo declaring >=3.11 runs its tests on 3.14 while the type checker, deriving
    # pythonVersion from that same line, checks 3.11.
    _declare(tmp_cwd, ">=3.11")
    _venv_on(tmp_cwd, "3.14.5")
    with pytest.raises(Exit) as exc_info:
        venv.check.body(c)
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "on Python 3.14, but this project declares 3.11" in out
    assert "inv venv.recreate" in out  # the fix, not just the finding


def test_check_reports_a_missing_venv(c, tmp_cwd, capsys):
    _declare(tmp_cwd, ">=3.11")
    with pytest.raises(Exit):
        venv.check.body(c)
    assert "no .venv" in capsys.readouterr().out


def test_check_has_nothing_to_check_without_a_declaration(c, tmp_cwd, capsys):
    _venv_on(tmp_cwd, "3.14.5")
    venv.check.body(c)  # no Exit — a project declaring no floor is not in a wrong state
    assert "nothing to check against" in capsys.readouterr().out


def test_check_never_writes(c, tmp_cwd):
    _declare(tmp_cwd, ">=3.11")
    _venv_on(tmp_cwd, "3.14.5")
    before = sorted(p.name for p in tmp_cwd.iterdir())
    with pytest.raises(Exit):
        venv.check.body(c)
    assert sorted(p.name for p in tmp_cwd.iterdir()) == before


def test_recreate_targets_the_declared_floor(c, tmp_cwd):
    _declare(tmp_cwd, ">=3.11")
    venv.recreate.body(c)
    c.run.assert_called_once_with("uv sync --locked --python 3.11", echo=True)


def test_recreate_python_overrides_the_declared_floor(c, tmp_cwd):
    _declare(tmp_cwd, ">=3.11")
    venv.recreate.body(c, python="3.13")
    c.run.assert_called_once_with("uv sync --locked --python 3.13", echo=True)


def test_recreate_refuses_without_a_declaration_or_an_explicit_version(c, tmp_cwd):
    # Nothing to target, and guessing would be the "one repo decides everyone's floor" failure in
    # miniature. Refuse and name the flag instead.
    with pytest.raises(Exit, match="no requires-python"):
        venv.recreate.body(c)


def test_pin_writes_the_declared_floor(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.delenv("UV_PYTHON", raising=False)
    _declare(tmp_cwd, ">=3.11")
    venv.pin.body(c)
    assert (tmp_cwd / ".python-version").read_text() == "3.11\n"
    assert "pins 3.11" in capsys.readouterr().out


def test_pin_rewrites_a_drifted_file_and_names_what_it_replaced(c, tmp_cwd, monkeypatch, capsys):
    # The state this task exists to correct, and the one a sibling repo is actually in: a
    # hand-written pin asserting an interpreter the project never declared.
    monkeypatch.delenv("UV_PYTHON", raising=False)
    _declare(tmp_cwd, ">=3.11")
    (tmp_cwd / ".python-version").write_text("3.14\n")
    venv.pin.body(c)
    assert (tmp_cwd / ".python-version").read_text() == "3.11\n"
    assert "pins 3.11 (was 3.14)" in capsys.readouterr().out


def test_pin_is_a_noop_when_already_correct(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.delenv("UV_PYTHON", raising=False)
    _declare(tmp_cwd, ">=3.11")
    (tmp_cwd / ".python-version").write_text("3.11\n")
    venv.pin.body(c)
    assert "already pins 3.11" in capsys.readouterr().out


def test_pin_says_when_uv_python_will_override_the_file(c, tmp_cwd, monkeypatch, capsys):
    # Writing the file and reporting success into a shell where uv ignores it is the failure mode
    # worth naming: measured, UV_PYTHON is an explicit request that outranks .python-version.
    monkeypatch.setenv("UV_PYTHON", "3.14")
    _declare(tmp_cwd, ">=3.11")
    venv.pin.body(c)
    out = capsys.readouterr().out
    assert (tmp_cwd / ".python-version").read_text() == "3.11\n"  # still written
    assert "UV_PYTHON=3.14 is set and overrides this file" in out


def test_pin_has_nothing_to_pin_without_a_declaration(c, tmp_cwd, capsys):
    venv.pin.body(c)
    assert not (tmp_cwd / ".python-version").exists()
    assert "nothing to pin" in capsys.readouterr().out


def test_check_reports_a_drifted_python_version_file(c, tmp_cwd, capsys):
    _declare(tmp_cwd, ">=3.11")
    _venv_on(tmp_cwd, "3.11.15")  # the venv is right; only the pin has drifted
    (tmp_cwd / ".python-version").write_text("3.14\n")
    with pytest.raises(Exit) as exc_info:
        venv.check.body(c)
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert ".python-version pins 3.14, but this project declares 3.11" in out
    assert "inv venv.pin" in out


def test_check_ignores_an_absent_python_version_file(c, tmp_cwd, capsys):
    # Optional by design: a repo without one is not misconfigured, so its absence is never a finding.
    _declare(tmp_cwd, ">=3.11")
    _venv_on(tmp_cwd, "3.11.15")
    venv.check.body(c)
    assert ".python-version" not in capsys.readouterr().out

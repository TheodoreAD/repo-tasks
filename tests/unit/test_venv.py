"""Tests for repo_tasks.venv: asserts the exact command string each task builds via invoke's
MockContext, plus `delete`'s real filesystem exists-check/rmtree behavior against tmp_path."""

from invoke import MockContext, Result

from repo_tasks import venv


def test_sync_default():
    c = MockContext(run=True)
    venv.sync.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv sync --locked", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_sync_no_editable():
    c = MockContext(run=True)
    venv.sync.body(c, no_editable=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv sync --locked --no-editable", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_sync_no_dev():
    c = MockContext(run=True)
    venv.sync.body(c, no_dev=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv sync --locked --no-dev", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_sync_no_install_project():
    c = MockContext(run=True)
    venv.sync.body(c, no_install_project=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "uv sync --locked --no-install-project", echo=True
    )


def test_sync_project_narrows_to_one_workspace_member():
    c = MockContext(run=True)
    venv.sync.body(c, project="sample-service")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv sync --locked --package sample-service", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_sync_all_flags_combined():
    c = MockContext(run=True)
    venv.sync.body(  # pyright: ignore[reportAny, reportFunctionMemberAccess]
        c, no_editable=True, no_dev=True, no_install_project=True
    )
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "uv sync --locked --no-editable --no-dev --no-install-project", echo=True
    )


def test_delete_noop_when_venv_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    c = MockContext()
    venv.delete.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "nothing to clean" in capsys.readouterr().out


def test_delete_removes_venv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".venv").mkdir()
    c = MockContext()
    venv.delete.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert not (tmp_path / ".venv").exists()


def test_install_wheel_default():
    c = MockContext(run=True)
    venv.install_wheel.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "uv pip install --no-deps dist/*.whl", echo=True
    )


def test_install_wheel_explicit_path():
    c = MockContext(run=Result())
    venv.install_wheel.body(c, wheel="dist/repo_tasks-0.1.0-py3-none-any.whl")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "uv pip install --no-deps dist/repo_tasks-0.1.0-py3-none-any.whl", echo=True
    )


def test_sync_does_not_touch_github_path_when_unset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_PATH", raising=False)
    c = MockContext(run=True)
    venv.sync.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    # No GITHUB_PATH file was ever created/written -- nothing to assert on disk beyond this not
    # raising, since there's no path to check.


def test_sync_registers_venv_bin_on_github_path_when_set(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    github_path_file = tmp_path / "github_path"
    github_path_file.touch()
    monkeypatch.setenv("GITHUB_PATH", str(github_path_file))
    c = MockContext(run=True)
    venv.sync.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert github_path_file.read_text() == f"{(tmp_path / '.venv' / 'bin').resolve()}\n"

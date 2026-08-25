"""Tests for repo_tasks.venv: asserts the exact command string each task builds via invoke's
MockContext, plus `delete`'s real filesystem exists-check/rmtree behavior against tmp_path."""

from invoke import MockContext, Result

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

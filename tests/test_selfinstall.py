"""Tests for repo_tasks.selfinstall: update/status/version/stamp — command-string construction
via MockContext (matching tests/test_gitflow.py's dict-keyed style for the git ls-remote call),
plus the stamped-file read/write roundtrip via tmp_path, network-free throughout."""

from invoke import MockContext, Result

from repo_tasks import selfinstall

_LS_REMOTE_CMD = f"git ls-remote --tags --refs --sort=-v:refname {selfinstall._REPO_URL} 'v*'"  # pyright: ignore[reportPrivateUsage]


def test_update_installs_latest_tag_when_tags_exist():
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}@v1.4.2'"  # pyright: ignore[reportPrivateUsage]
    c = MockContext(
        run={
            _LS_REMOTE_CMD: Result(stdout="refs/tags/v1.4.2\nrefs/tags/v1.4.1\n", exited=0),
            install_cmd: Result(exited=0),
        }
    )
    selfinstall.update.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_any_call(install_cmd, echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_update_falls_back_to_default_branch_when_no_tags_exist(capsys):
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}'"  # pyright: ignore[reportPrivateUsage]
    c = MockContext(run={_LS_REMOTE_CMD: Result(stdout="", exited=0), install_cmd: Result(exited=0)})
    selfinstall.update.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_any_call(install_cmd, echo=True)  # pyright: ignore[reportAttributeAccessIssue]
    assert "no tagged release found yet" in capsys.readouterr().out


def test_version_prints_installed_version(monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.version.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.strip() == "1.2.3"


def test_stamp_writes_pinned_install_script(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    script = tmp_path / "bootstrap-repo-tasks.sh"
    assert script.exists()
    text = script.read_text()
    assert f"repo-tasks @ git+{selfinstall._REPO_URL}@v1.2.3'" in text  # pyright: ignore[reportPrivateUsage]
    assert script.stat().st_mode & 0o111  # executable


def test_status_reports_no_stamp_yet(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "no stamped bootstrap-repo-tasks.sh yet" in capsys.readouterr().out


def test_status_reports_up_to_date(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "up to date" in capsys.readouterr().out


def test_status_reports_drift(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.3.0")
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "drift" in capsys.readouterr().out

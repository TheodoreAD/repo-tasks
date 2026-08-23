"""Tests for repo_tasks.selfinstall: update/status/version/stamp — command-string construction
via MockContext (matching tests/test_gitflow.py's dict-keyed style for the git ls-remote call),
plus the stamped-file read/write roundtrip via tmp_path, network-free throughout."""

from invoke import MockContext, Result

from repo_tasks import selfinstall

_LS_REMOTE_CMD = f"git ls-remote --tags --refs --sort=-v:refname {selfinstall._REPO_URL} 'v*'"  # pyright: ignore[reportPrivateUsage]


def _ls_remote(*refs: str) -> dict[str, Result]:
    stdout = "".join(f"refs/tags/{ref}\n" for ref in refs)
    return {_LS_REMOTE_CMD: Result(stdout=stdout, exited=0)}


def test_update_installs_latest_tag_when_tags_exist():
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}@v1.4.2'"  # pyright: ignore[reportPrivateUsage]
    c = MockContext(run={**_ls_remote("v1.4.2", "v1.4.1"), install_cmd: Result(exited=0)})
    selfinstall.update.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_any_call(install_cmd, echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_update_falls_back_to_default_branch_when_no_tags_exist(capsys):
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}'"  # pyright: ignore[reportPrivateUsage]
    c = MockContext(run={**_ls_remote(), install_cmd: Result(exited=0)})
    selfinstall.update.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_any_call(install_cmd, echo=True)  # pyright: ignore[reportAttributeAccessIssue]
    assert "no tagged release found yet" in capsys.readouterr().out


def test_version_prints_installed_version(monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.version.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.strip() == "1.2.3"


def test_stamp_writes_pinned_install_script_when_tag_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    c = MockContext(run=_ls_remote("v1.2.3", "v1.0.0"))
    selfinstall.stamp.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    script = tmp_path / "bootstrap-repo-tasks.sh"
    assert script.exists()
    text = script.read_text()
    assert f"repo-tasks @ git+{selfinstall._REPO_URL}@v1.2.3'" in text  # pyright: ignore[reportPrivateUsage]
    assert script.stat().st_mode & 0o111  # executable


def test_stamp_falls_back_to_unpinned_when_no_matching_tag(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    # Only an older tag exists upstream -- v1.2.3 (this checkout's own version) isn't released yet.
    c = MockContext(run=_ls_remote("v1.0.0"))
    selfinstall.stamp.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    text = (tmp_path / "bootstrap-repo-tasks.sh").read_text()
    assert f"repo-tasks @ git+{selfinstall._REPO_URL}'" in text  # pyright: ignore[reportPrivateUsage]
    assert "@v1.2.3" not in text
    assert "isn't a real upstream tag yet" in capsys.readouterr().out


def test_status_reports_no_stamp_yet(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "no stamped bootstrap-repo-tasks.sh yet" in capsys.readouterr().out


def test_status_reports_unpinned_when_stamped_without_a_tag(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote()))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "nothing to compare a version against" in capsys.readouterr().out


def test_status_reports_up_to_date(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote("v1.2.3")))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "up to date" in capsys.readouterr().out


def test_status_reports_drift(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote("v1.2.3")))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.3.0")
    selfinstall.status.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "drift" in capsys.readouterr().out

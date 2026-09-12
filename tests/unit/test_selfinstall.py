"""Tests for repo_tasks.selfinstall: update/status/version/stamp — command-string construction
via MockContext (matching tests/test_gitflow.py's dict-keyed style for the git ls-remote call),
plus the stamped-file read/write roundtrip via tmp_path, network-free throughout."""

from invoke import MockContext, Result

from repo_tasks import selfinstall

_LS_REMOTE_CMD = f"git ls-remote --tags --refs --sort=-v:refname {selfinstall._REPO_URL} 'v*'"


def _ls_remote(*refs: str) -> dict[str, Result]:
    stdout = "".join(f"refs/tags/{ref}\n" for ref in refs)
    return {_LS_REMOTE_CMD: Result(stdout=stdout, exited=0)}


def _tool_list(*lines: str) -> dict[str, Result]:
    """`uv tool list` output: one `<name> v<version>` line per tool, its executables under it as
    `- <name>`."""
    return {selfinstall._TOOL_LIST_CMD: Result(stdout="".join(f"{line}\n" for line in lines), exited=0)}


_REPO_TASKS_ALONE = ("repo-tasks v1.4.2", "- inv", "- invoke", "- repo-tasks")


def test_update_installs_latest_tag_when_tags_exist():
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}@v1.4.2'"
    runs = {**_ls_remote("v1.4.2", "v1.4.1"), **_tool_list(*_REPO_TASKS_ALONE), install_cmd: Result(exited=0)}
    c = MockContext(run=runs)
    selfinstall.update.body(c)
    c.run.assert_any_call(install_cmd, echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_update_falls_back_to_default_branch_when_no_tags_exist(capsys):
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}'"
    c = MockContext(run={**_ls_remote(), **_tool_list(*_REPO_TASKS_ALONE), install_cmd: Result(exited=0)})
    selfinstall.update.body(c)
    c.run.assert_any_call(install_cmd, echo=True)  # pyright: ignore[reportAttributeAccessIssue]
    assert "no tagged release found yet" in capsys.readouterr().out


def test_update_reports_a_separately_installed_invoke_tool(capsys):
    """The machine state that breaks every family repo at once: two uv tools both shipping `inv`,
    with uv marking neither as shadowed."""
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}@v1.4.2'"
    listing = _tool_list(*_REPO_TASKS_ALONE, "invoke v3.0.3", "- inv", "- invoke")
    c = MockContext(run={**_ls_remote("v1.4.2"), **listing, install_cmd: Result(exited=0)})
    selfinstall.update.body(c)
    out = capsys.readouterr().out
    assert "invoke 3.0.3 is also installed as a uv tool of its own" in out
    # Reported, never removed -- `uv tool uninstall` is the human's to run, and only as a next step.
    assert "uv tool uninstall invoke" in out
    for call in c.run.call_args_list:  # pyright: ignore[reportAttributeAccessIssue]
        assert "uninstall" not in call.args[0]


def test_update_does_not_read_repo_tasks_own_invoke_executable_as_a_second_tool(capsys):
    """`repo-tasks` ships `inv` and `invoke` itself, via `--with-executables-from invoke`. Those
    lines are what a conflict looks like from the outside, and they are the ordinary case."""
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}@v1.4.2'"
    runs = {**_ls_remote("v1.4.2"), **_tool_list(*_REPO_TASKS_ALONE), install_cmd: Result(exited=0)}
    selfinstall.update.body(MockContext(run=runs))
    assert "also installed as a uv tool" not in capsys.readouterr().out


def test_update_says_nothing_about_shadowing_when_uv_cannot_list_tools(capsys):
    """The install already succeeded, so a listing that fails answers nothing either way — and
    inventing a warning from it would be worse than staying quiet."""
    install_cmd = f"{selfinstall._INSTALL_CMD} 'repo-tasks @ git+{selfinstall._REPO_URL}@v1.4.2'"
    runs = {
        **_ls_remote("v1.4.2"),
        selfinstall._TOOL_LIST_CMD: Result(stdout="", exited=127),
        install_cmd: Result(exited=0),
    }
    selfinstall.update.body(MockContext(run=runs))
    assert "also installed as a uv tool" not in capsys.readouterr().out


def test_installed_tools_does_not_read_an_executable_line_as_a_tool():
    """The parse has to tell a tool heading from the executables listed under it, and an executable
    whose name starts with `v` is what a looser one gets wrong: `- vhs` reads as the tool `-` at
    version `hs`."""
    c = MockContext(run=_tool_list("charm-tools v1.0.0", "- vhs", "- freeze"))
    assert selfinstall._installed_tools(c) == {"charm-tools": "1.0.0"}


def test_installed_tools_separates_uv_failing_from_uv_having_nothing():
    """None and an empty dict mean different things: `_report_a_shadowing_invoke_tool` has to stay
    quiet on the first and is entitled to an answer on the second."""
    assert selfinstall._installed_tools(MockContext(run={selfinstall._TOOL_LIST_CMD: Result(exited=127)})) is None
    assert selfinstall._installed_tools(MockContext(run=_tool_list())) == {}


def test_version_prints_installed_version(c, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.version.body(c)
    assert capsys.readouterr().out.strip() == "1.2.3"


def test_stamp_writes_pinned_install_script_when_tag_exists(tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    c = MockContext(run=_ls_remote("v1.2.3", "v1.0.0"))
    selfinstall.stamp.body(c)
    script = tmp_cwd / "bootstrap-repo-tasks.sh"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert f"repo-tasks @ git+{selfinstall._REPO_URL}@v1.2.3'" in text
    assert script.stat().st_mode & 0o111  # executable
    # Which source the number came from, on every run: the pin is only readable if you know that.
    assert "active version 1.2.3, read from the interpreter running this task" in capsys.readouterr().out


def test_stamp_warns_when_the_active_version_is_behind_the_latest_release(tmp_cwd, monkeypatch, capsys):
    """The case that prompted the warning: an editable install whose recorded metadata is stale
    reads as an ordinary version and pins consumers to a genuinely older release."""
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    c = MockContext(run=_ls_remote("v2.0.0", "v1.2.3"))
    selfinstall.stamp.body(c)
    text = (tmp_cwd / "bootstrap-repo-tasks.sh").read_text(encoding="utf-8")
    # Still pinned to the active version -- the warning informs, it does not override the source.
    assert f"repo-tasks @ git+{selfinstall._REPO_URL}@v1.2.3'" in text
    assert "v1.2.3 is behind the latest release v2.0.0" in capsys.readouterr().out


def test_stamp_falls_back_to_unpinned_when_no_matching_tag(tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    # Only an older tag exists upstream -- v1.2.3 (this checkout's own version) isn't released yet.
    c = MockContext(run=_ls_remote("v1.0.0"))
    selfinstall.stamp.body(c)
    text = (tmp_cwd / "bootstrap-repo-tasks.sh").read_text(encoding="utf-8")
    assert f"repo-tasks @ git+{selfinstall._REPO_URL}'" in text
    assert "@v1.2.3" not in text
    assert "isn't a real upstream tag" in capsys.readouterr().out


def test_stamp_says_an_empty_tag_list_has_two_causes(tmp_cwd, monkeypatch, capsys):
    """`_remote_tags` runs under `warn=True`, so an unreachable remote and a repo nobody has tagged
    return the same empty list — and both stamp an unpinned script. Naming one of them would be a
    guess, so the message names both."""
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote()))
    text = (tmp_cwd / "bootstrap-repo-tasks.sh").read_text(encoding="utf-8")
    assert "@v1.2.3" not in text
    out = capsys.readouterr().out
    assert "nothing is tagged yet, or the remote was unreachable" in out


def test_status_reports_the_global_install_alongside_the_active_one(tmp_cwd, monkeypatch, capsys):
    """The whole point: two numbers, named, because only one used to be printed."""
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "0.2.0")
    c = MockContext(run=_tool_list("repo-tasks v0.3.0", "- inv", "- repo-tasks", "shfmt-py v4.0.0"))
    selfinstall.status.body(c)
    out = capsys.readouterr().out
    assert "active: 0.2.0 (this process)" in out
    assert "global uv tool: 0.3.0 (differs)" in out


def test_status_says_so_when_the_two_agree(tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "0.3.0")
    c = MockContext(run=_tool_list("repo-tasks v0.3.0", "- inv"))
    selfinstall.status.body(c)
    assert "global uv tool: 0.3.0 (same)" in capsys.readouterr().out


def test_status_does_not_treat_a_missing_global_install_as_an_error(tmp_cwd, monkeypatch, capsys):
    """A consumer taking repo-tasks as a project dependency legitimately has no tool install."""
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "0.3.0")
    c = MockContext(run=_tool_list("shfmt-py v4.0.0", "- shfmt"))
    selfinstall.status.body(c)
    assert "not installed, or uv unavailable" in capsys.readouterr().out


def test_status_survives_uv_being_absent(tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "0.3.0")
    c = MockContext(run={selfinstall._TOOL_LIST_CMD: Result(stdout="", exited=127)})
    selfinstall.status.body(c)
    out = capsys.readouterr().out
    assert "not installed, or uv unavailable" in out
    assert "active: 0.3.0" in out  # the reading that does not need uv still lands


def test_status_reports_no_stamp_yet(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.status.body(c)
    assert "no stamped bootstrap-repo-tasks.sh yet" in capsys.readouterr().out


def test_status_reports_unpinned_when_stamped_without_a_tag(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote()))
    selfinstall.status.body(c)
    assert "nothing to compare a version against" in capsys.readouterr().out


def test_status_reports_up_to_date(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote("v1.2.3")))
    selfinstall.status.body(c)
    assert "up to date" in capsys.readouterr().out


def test_status_reports_drift(c, tmp_cwd, monkeypatch, capsys):
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.2.3")
    selfinstall.stamp.body(MockContext(run=_ls_remote("v1.2.3")))
    monkeypatch.setattr(selfinstall, "_installed_version", lambda name: "1.3.0")
    selfinstall.status.body(c)
    assert "drift" in capsys.readouterr().out

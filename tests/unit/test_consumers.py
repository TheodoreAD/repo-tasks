"""`consumers.diff` — the read-only cross-repo drift report.

The behaviour worth pinning is mostly about what it refuses to do: derive its own consumer list,
skip a declared consumer silently, or write anything into a tree it is only reading.
"""

import re
import tomllib
from pathlib import Path
from typing import cast

import pytest
from invoke import MockContext, Result
from invoke.exceptions import Exit

from repo_tasks import consumers, projects
from repo_tasks.configs import Drift  # where it is defined; `consumers` only re-exports it

_REPO_TASKS_TOML = '[[consumer]]\nname = "alpha"\n\n[[consumer]]\nname = "beta"\n'

_SECURITY_HEAD = "a" * 40
_GIT_LOG = f"git log -1 --format=%H -- {consumers._SECURITY_REUSABLE}"


def _ctx(head: str = _SECURITY_HEAD) -> MockContext:
    """A context answering the one command `diff` shells out to.

    That is the local `git log` reading this repo's own `security-reusable.yml` head, so a consumer's
    caller pin can be compared against something real. A dict-valued `run` is deliberate: anything
    else this task starts shelling out to fails loudly here rather than being absorbed, which is the
    property that caught this call being added in the first place."""
    return MockContext(run={_GIT_LOG: Result(stdout=f"{head}\n", exited=0)})


def _declare(root: Path, toml: str) -> None:
    (root / "repo-tasks.toml").write_text(toml, encoding="utf-8")


def _snapshot(root: Path) -> dict[str, str]:
    """Every file under `root`, by relative path and content — the read-only contract as one value.

    Stronger than listing the top level, and it survives the reporter learning to read a new file:
    the assertion is that nothing *changed*, not that the tree holds a particular set of names."""
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _consumer_tree(parent: Path, name: str, *, security: str | None = _SECURITY_HEAD) -> Path:
    """A scratch consumer. `security` gives it a workflow calling the shipped reusable security
    workflow at that ref — the default, because a tree with no `.github/` at all is its own reported
    finding and would otherwise show up in every test that only means "nothing to report"."""
    path = parent / name
    path.mkdir(parents=True)
    if security is not None:
        workflows = path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "security.yml").write_text(
            f"jobs:\n  security:\n    uses: TheodoreAD/repo-tasks/{consumers._SECURITY_REUSABLE}@{security}\n",
            encoding="utf-8",
        )
    return path


# ---------------------------------------------------------------------------
# discovery: declared, never derived
# ---------------------------------------------------------------------------


def test_consumers_come_from_declared_entries(tmp_cwd, monkeypatch):
    _declare(tmp_cwd, _REPO_TASKS_TOML)
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    assert [c.name for c in projects.discover_consumers()] == ["alpha", "beta"]


def test_a_repo_that_looks_like_a_consumer_is_not_one_unless_declared(tmp_cwd, monkeypatch):
    """The whole point of declaring the list. Three attempts to derive it each encoded a path shape
    some real consumer did not have, and a derived list that misses one reports success."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    undeclared = _consumer_tree(tmp_cwd, "looks-like-one")
    (undeclared / "tasks.py").write_text("from repo_tasks import ns\n", encoding="utf-8")
    assert [c.name for c in projects.discover_consumers()] == ["alpha"]


def test_no_entries_means_no_consumers(tmp_cwd):
    _declare(tmp_cwd, '[[docker]]\nname = "x"\npath = "."\ndockerfile = "D"\nimage = "i"\n')
    assert projects.discover_consumers() == []


def test_projects_root_defaults_to_this_repos_parent(tmp_cwd, monkeypatch):
    monkeypatch.delenv("REPO_TASKS_PROJECTS_ROOT", raising=False)
    assert projects.projects_root() == tmp_cwd.parent


def test_an_entry_may_name_a_checkout_outside_the_root(tmp_cwd, monkeypatch):
    """The escape hatch for a consumer that does not sit beside the others."""
    elsewhere = tmp_cwd / "somewhere" / "else"
    elsewhere.mkdir(parents=True)
    _declare(tmp_cwd, f'[[consumer]]\nname = "alpha"\npath = "{elsewhere}"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    assert projects.discover_consumers()[0].path == elsewhere


def test_an_entry_with_no_name_names_the_file_and_the_table(tmp_cwd):
    _declare(tmp_cwd, '[[consumer]]\npath = "somewhere"\n')
    with pytest.raises(ValueError, match=r"repo-tasks\.toml: a \[\[consumer\]\] entry declares no name"):
        projects.discover_consumers()


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def test_a_declared_consumer_with_no_checkout_is_named_not_skipped(tmp_cwd, monkeypatch, capsys):
    """A silent skip would put the reporter back where the hand-kept list was: reporting success
    for a consumer it never looked at."""
    _declare(tmp_cwd, '[[consumer]]\nname = "gone"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    with pytest.raises(Exit) as excinfo:
        consumers.diff.body(_ctx())
    assert excinfo.value.code == 1
    assert "gone: NOT FOUND" in capsys.readouterr().out


def test_nothing_declared_is_not_a_failure(tmp_cwd, capsys):
    """Every consumer of this package publishes the task and declares no entries, so the empty case
    is the common one and must not be an error there."""
    _declare(tmp_cwd, "")
    consumers.diff.body(_ctx())
    assert "nothing to measure" in capsys.readouterr().out


def test_an_unknown_name_is_an_error_not_an_empty_run(tmp_cwd, monkeypatch):
    """A typo must not look like a clean report."""
    _declare(tmp_cwd, _REPO_TASKS_TOML)
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    with pytest.raises(Exit, match=r"entry named 'gamma' in repo-tasks\.toml"):
        consumers.diff.body(_ctx(), name="gamma")


def test_the_report_names_the_version_it_measured_with(tmp_cwd, monkeypatch, capsys):
    """A per-consumer answer only means something against a named version of this package —
    otherwise two rows measured by different tools sit in one table saying nothing."""
    _declare(tmp_cwd, '[[consumer]]\nname = "gone"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "measured with repo-tasks" in capsys.readouterr().out


def test_a_consumer_carrying_the_shipped_configs_reports_up_to_date(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha")
    before = _snapshot(alpha)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(_ctx())
    assert "alpha: up to date" in capsys.readouterr().out
    assert _snapshot(alpha) == before, "read-only: nothing written into the consumer's tree"


def test_a_drifted_consumer_reports_each_kind_of_drift(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha")
    drift = Drift(["ruff.toml"], ["pytest-socket"], ["hadolint-py!=2.15.1.2"], None)
    monkeypatch.setattr(consumers, "_measure", lambda *_: drift)
    with pytest.raises(Exit) as excinfo:
        consumers.diff.body(_ctx())
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "config files behind: ruff.toml" in out
    assert "dev group missing: pytest-socket" in out
    assert "declared without the manifest's constraint: hadolint-py!=2.15.1.2" in out


def test_the_self_referential_skip_is_reported_where_it_applies(tmp_cwd, monkeypatch, capsys):
    """Otherwise the one repo whose maintainer needs to know the manifest still carries the entry
    cannot tell it from the entry having been dropped."""
    _declare(tmp_cwd, '[[consumer]]\nname = "invoke-stubs"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "invoke-stubs")
    drift = Drift(["ruff.toml"], [], [], "invoke-stubs @ git+https://example.invalid/invoke-stubs")
    monkeypatch.setattr(consumers, "_measure", lambda *_: drift)
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "skipped an entry naming invoke-stubs itself" in capsys.readouterr().out


def test_one_consumer_being_clean_does_not_hide_another_being_behind(tmp_cwd, monkeypatch, capsys):
    """The loop's whole value is the comparison, so an early clean row must not short-circuit it."""
    _declare(tmp_cwd, _REPO_TASKS_TOML)
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha")
    _consumer_tree(tmp_cwd, "beta")
    drifts = {"alpha": Drift([], [], [], None), "beta": Drift(["pytest.ini"], [], [], None)}
    monkeypatch.setattr(consumers, "_measure", lambda consumer, _source: drifts[consumer.name])
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    out = capsys.readouterr().out
    assert "alpha: up to date" in out
    assert "beta: config files behind: pytest.ini" in out


# ---------------------------------------------------------------------------
# the bootstrap pin: the one drift no config comparison can reach
# ---------------------------------------------------------------------------


def _bootstrap(root: Path, pinned: str | None) -> None:
    ref = f"@v{pinned}" if pinned else ""
    (root / "bootstrap-repo-tasks.sh").write_text(
        f"uv tool install 'repo-tasks @ git+https://github.com/TheodoreAD/repo-tasks{ref}'\n", encoding="utf-8"
    )


def test_a_consumer_with_no_bootstrap_script_is_not_reported_unpinned(tmp_cwd, monkeypatch, capsys):
    """It pins through its own lock, so there is no script and nothing to say — the distinction the
    reporter would lose if "no version" were one state instead of two."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(_ctx())
    out = capsys.readouterr().out
    assert "alpha: up to date" in out
    assert "bootstrap" not in out


def test_an_unpinned_bootstrap_is_behind_even_with_every_config_current(tmp_cwd, monkeypatch, capsys):
    """The state that made a push here a deploy, and the one `configs.diff` structurally cannot see:
    it compares shipped config files and the dev group, and the pin is in neither. Before this, a
    consumer swept without the stamp step looked identical to one swept with it."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _bootstrap(_consumer_tree(tmp_cwd, "alpha"), pinned=None)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit) as excinfo:
        consumers.diff.body(_ctx())
    assert excinfo.value.code == 1
    assert "alpha: bootstrap unpinned" in capsys.readouterr().out


def test_a_bootstrap_pinned_to_the_measured_version_is_up_to_date(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _bootstrap(_consumer_tree(tmp_cwd, "alpha"), pinned="9.9.9")
    monkeypatch.setattr(consumers, "_measured_version", lambda: "9.9.9")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(_ctx())
    assert "alpha: up to date" in capsys.readouterr().out


def test_a_bootstrap_pinned_to_an_older_version_names_both(tmp_cwd, monkeypatch, capsys):
    """Compared against the version this run measured with, not the newest upstream tag — that needs
    the network, and every other line in the same report was produced by the measured one."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _bootstrap(_consumer_tree(tmp_cwd, "alpha"), pinned="0.2.0")
    monkeypatch.setattr(consumers, "_measured_version", lambda: "0.3.0")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "bootstrap pinned to v0.2.0, behind the v0.3.0 this was measured with" in capsys.readouterr().out


def test_the_pin_is_reported_alongside_config_drift_not_instead_of_it(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _bootstrap(_consumer_tree(tmp_cwd, "alpha"), pinned=None)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift(["ruff.toml"], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    out = capsys.readouterr().out
    assert "config files behind: ruff.toml" in out
    assert "bootstrap unpinned" in out


def test_reading_the_pin_writes_nothing_into_the_consumer(tmp_cwd, monkeypatch):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha")
    _bootstrap(alpha, pinned=None)
    before = _snapshot(alpha)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert _snapshot(alpha) == before, "the unpinned script is read and never corrected"


# ---------------------------------------------------------------------------
# the lock pin: a consumer declaring repo-tasks from git itself, with no bootstrap
# ---------------------------------------------------------------------------


def _run_alpha(tmp_cwd: Path, monkeypatch: pytest.MonkeyPatch, pyproject: str, measured: str = "0.6.0") -> None:
    """One consumer, clean on every other line, whose only finding can be its declared pin."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    (_consumer_tree(tmp_cwd, "alpha") / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    monkeypatch.setattr(consumers, "_measured_version", lambda: measured)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))


def test_a_uv_source_with_no_tag_is_behind(tmp_cwd, monkeypatch, capsys):
    """The state both lock-pinning consumers were in until 2026-09-28: a bare git source, so every
    `deps.lock --package repo-tasks` resolved `main` while the sweep doc called it the equivalent of
    `stamp`. Nothing reported it, because the only pin this file read was a bootstrap's."""
    _run_alpha(
        tmp_cwd,
        monkeypatch,
        '[tool.uv.sources]\nrepo-tasks = { git = "https://github.com/TheodoreAD/repo-tasks" }\n',
    )
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "alpha: repo-tasks declared from git with no tag" in capsys.readouterr().out


def test_a_direct_reference_at_the_measured_tag_is_up_to_date(tmp_cwd, monkeypatch, capsys):
    _run_alpha(
        tmp_cwd,
        monkeypatch,
        '[dependency-groups]\ndev = ["repo-tasks @ git+https://github.com/TheodoreAD/repo-tasks@v0.6.0"]\n',
    )
    consumers.diff.body(_ctx())
    assert "alpha: up to date" in capsys.readouterr().out


def test_a_uv_source_at_an_older_tag_names_both(tmp_cwd, monkeypatch, capsys):
    _run_alpha(
        tmp_cwd,
        monkeypatch,
        '[tool.uv.sources]\nrepo-tasks = { git = "https://github.com/TheodoreAD/repo-tasks", tag = "v0.5.0" }\n',
    )
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "repo-tasks declared at v0.5.0, behind the v0.6.0 this was measured with" in capsys.readouterr().out


def test_a_branch_is_a_ref_but_not_a_release(tmp_cwd, monkeypatch, capsys):
    """Naming `main` explicitly is the same drift as naming nothing, and says so differently."""
    _run_alpha(
        tmp_cwd,
        monkeypatch,
        '[project]\ndependencies = ["repo-tasks @ git+https://github.com/TheodoreAD/repo-tasks@main"]\n',
    )
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "repo-tasks declared at 'main', not a release tag" in capsys.readouterr().out


def test_the_user_in_an_ssh_url_is_not_read_as_a_ref(tmp_cwd, monkeypatch, capsys):
    """`git@github.com` carries an `@` too. Only one in the URL's last path segment is a ref."""
    _run_alpha(
        tmp_cwd,
        monkeypatch,
        '[dependency-groups]\ndev = ["repo-tasks @ git+ssh://git@github.com/TheodoreAD/repo-tasks"]\n',
    )
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "repo-tasks declared from git with no tag" in capsys.readouterr().out


def test_a_consumer_not_declaring_repo_tasks_from_git_has_no_lock_pin(tmp_cwd, monkeypatch, capsys):
    """A registry requirement, or none at all, is not something this reads — the global-tool
    consumers declare no repo-tasks, and a version specifier is the resolver's job, not a pin."""
    _run_alpha(tmp_cwd, monkeypatch, '[project]\ndependencies = ["repo-tasks>=0.5"]\n')
    consumers.diff.body(_ctx())
    assert "alpha: up to date" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the security-workflow caller: an addition to a consumer, so nothing compares it
# ---------------------------------------------------------------------------


def test_a_consumer_with_workflows_but_no_caller_is_behind(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha", security=None)
    workflows = alpha / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("jobs:\n  ci:\n    steps:\n      - uses: actions/checkout@v7\n", encoding="utf-8")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert f"no caller for {consumers._SECURITY_REUSABLE}" in capsys.readouterr().out


def _ci_without_caller(tmp_cwd: Path, monkeypatch: pytest.MonkeyPatch, repo_tasks_toml: str) -> None:
    """One consumer with CI but no security caller, declaring `repo_tasks_toml` in its own tree."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha", security=None)
    (alpha / ".github" / "workflows").mkdir(parents=True)
    (alpha / ".github" / "workflows" / "ci.yml").write_text("jobs: {}\n", encoding="utf-8")
    (alpha / "repo-tasks.toml").write_text(repo_tasks_toml, encoding="utf-8")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))


def test_a_declined_caller_is_said_with_its_reason_and_not_counted(tmp_cwd, monkeypatch, capsys):
    """agent-skills decided against the caller because nothing in its lock ships to anyone, and was
    reported as missing one on every run anyway, with the reason living only in its own plan. The
    declaration puts the answer where the report can print it."""
    _ci_without_caller(tmp_cwd, monkeypatch, '[security]\ncaller = false\nreason = "the lock ships nothing"\n')
    consumers.diff.body(_ctx())  # no Exit: a settled question is not drift
    assert "alpha: declines the security caller: the lock ships nothing" in capsys.readouterr().out


def test_declining_without_a_reason_is_still_behind(tmp_cwd, monkeypatch, capsys):
    """The reason is the whole value of the declaration. Without it the next sweep cannot tell a
    settled opt-out from a forgotten one, so a bare `caller = false` does not silence the report."""
    _ci_without_caller(tmp_cwd, monkeypatch, "[security]\ncaller = false\n")
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "declines the security caller with no `reason`" in capsys.readouterr().out


def test_a_caller_present_is_checked_even_where_one_is_declined(tmp_cwd, monkeypatch, capsys):
    """A stale declaration never hides a real pin: the caller that exists is what CI runs."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha", security="b" * 40)
    (alpha / "repo-tasks.toml").write_text('[security]\ncaller = false\nreason = "x"\n', encoding="utf-8")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx(head="c" * 40))
    assert "security caller pinned to bbbbbbb" in capsys.readouterr().out


def test_the_caller_is_found_by_content_not_by_filename(tmp_cwd, monkeypatch, capsys):
    """This plan's own recurring mistake is letting a filename stand in for what it usually holds —
    the consumer set was miscounted three times that way. A caller in `audit.yml` counts."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha", security=None)
    workflows = alpha / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "audit.yml").write_text(
        f"jobs:\n  audit:\n    uses: TheodoreAD/repo-tasks/{consumers._SECURITY_REUSABLE}@{_SECURITY_HEAD}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(_ctx())
    assert "alpha: up to date" in capsys.readouterr().out


def test_a_caller_pinned_to_an_older_commit_names_both(tmp_cwd, monkeypatch, capsys):
    """The silent-staleness case: the file exists, the pin is a proper SHA, and nothing anywhere
    compares it against the workflow it names."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha", security="b" * 40)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx(head="c" * 40))
    assert "security caller pinned to bbbbbbb, the reusable workflow is at ccccccc" in capsys.readouterr().out


def test_a_caller_pinned_to_a_tag_is_reported_as_not_a_sha(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha", security="main")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert "security caller pinned to 'main', not a 40-character SHA" in capsys.readouterr().out


def test_no_ci_at_all_is_said_but_not_counted_as_behind(tmp_cwd, monkeypatch, capsys):
    """A consumer with no `.github/` — `invoke-stubs` until before the v0.6.0 sweep — cannot take a
    caller until somebody decides whether that repo has CI. Calling it behind would assert the
    answer; saying nothing would lose the one repo where a green local gate is the whole of the
    evidence."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha", security=None)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(_ctx())  # no Exit: reported, not counted
    assert "alpha: no CI at all, so nothing calls the security workflow" in capsys.readouterr().out


def test_no_ci_does_not_mask_real_drift_in_the_same_consumer(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha", security=None)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift(["ruff.toml"], [], [], None))
    with pytest.raises(Exit) as excinfo:
        consumers.diff.body(_ctx())
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "config files behind: ruff.toml" in out
    assert "no CI at all" in out


def test_the_currency_half_is_skipped_when_the_git_read_fails(tmp_cwd, monkeypatch, capsys):
    """A shallow clone or a non-git checkout is a reason to skip the comparison, never to fail the
    report — the presence half still answers, which is the more valuable of the two."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha", security="b" * 40)
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(MockContext(run={_GIT_LOG: Result(stdout="", exited=128)}))
    assert "alpha: up to date" in capsys.readouterr().out


def test_the_canary_workflow_checks_out_a_declared_consumer():
    """The reporter measures every consumer and runs none of them; `.github/workflows/canary.yml` is
    the other half — it runs one consumer's own tier against the ref being pushed, because that
    consumer's e2e is the only thing in the family testing what a generated repo does.

    Nothing connects the two files at run time, and they spell the same repo differently: the
    workflow needs a GitHub `owner/repo`, `repo-tasks.toml` declares a bare name. So dropping or
    renaming the `[[consumer]]` entry would leave the canary checking out a repo this package no
    longer counts as a consumer, with both files still passing everything else."""
    # Anchored to this file rather than to cwd, like test_deps.py's workflow check: the tier's
    # `tmp_cwd` fixture means cwd is a scratch directory, and these are the repo's own two files.
    repo_root = Path(__file__).parents[2]
    with (repo_root / "repo-tasks.toml").open("rb") as f:
        parsed = cast(dict[str, object], tomllib.load(f))
    declared = {entry["name"] for entry in cast(list[dict[str, object]], parsed.get("consumer", []))}

    workflow = (repo_root / ".github/workflows/canary.yml").read_text(encoding="utf-8")
    checked_out = cast(list[str], re.findall(r"^\s*repository:\s*(\S+)\s*$", workflow, re.MULTILINE))

    assert checked_out, "canary.yml checks out no second repository, so it canaries nothing"
    for repo in checked_out:
        assert repo.rsplit("/", 1)[-1] in declared, (
            f"canary.yml checks out {repo}, which repo-tasks.toml declares no [[consumer]] entry "
            f"for. Declare it, or point the canary at a repo that is one — a canary run against a "
            f"repo nobody calls a consumer proves nothing about the consumers."
        )


def test_an_unparseable_pyproject_is_one_consumers_line_not_the_end_of_the_run(tmp_cwd, monkeypatch, capsys):
    """The state an older ensure-deps left behind. A traceback here would end the loop before the
    consumers after it were measured, so the report would say nothing about them at all."""
    _declare(tmp_cwd, _REPO_TASKS_TOML)
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha")
    corrupted = '[dependency-groups]\ndev = [\n  "a[st  "ruff",\nore]",\n]\n'
    (alpha / "pyproject.toml").write_text(corrupted, encoding="utf-8")
    _consumer_tree(tmp_cwd, "beta")
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    out = capsys.readouterr().out
    assert "alpha: pyproject.toml does not parse as TOML" in out
    assert "[consumers.diff] beta:" in out, "the consumer after the broken one was never measured"


def test_measuring_restores_the_working_directory(tmp_cwd, monkeypatch):
    """`_measure` chdirs into each consumer, so a failure to restore would leave every later task in
    this process reading the wrong tree — and the tasks that write would write there."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha")
    before = Path.cwd()
    with pytest.raises(Exit):
        consumers.diff.body(_ctx())
    assert Path.cwd() == before

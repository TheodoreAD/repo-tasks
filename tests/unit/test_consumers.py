"""`consumers.diff` — the read-only cross-repo drift report.

The behaviour worth pinning is mostly about what it refuses to do: derive its own consumer list,
skip a declared consumer silently, or write anything into a tree it is only reading.
"""

from pathlib import Path

import pytest
from invoke import MockContext
from invoke.exceptions import Exit

from repo_tasks import consumers, projects
from repo_tasks.configs import Drift  # where it is defined; `consumers` only re-exports it

_REPO_TASKS_TOML = '[[consumer]]\nname = "alpha"\n\n[[consumer]]\nname = "beta"\n'


def _declare(root: Path, toml: str) -> None:
    (root / "repo-tasks.toml").write_text(toml, encoding="utf-8")


def _consumer_tree(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir(parents=True)
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
        consumers.diff.body(MockContext())
    assert excinfo.value.code == 1
    assert "gone: NOT FOUND" in capsys.readouterr().out


def test_nothing_declared_is_not_a_failure(tmp_cwd, capsys):
    """Every consumer of this package publishes the task and declares no entries, so the empty case
    is the common one and must not be an error there."""
    _declare(tmp_cwd, "")
    consumers.diff.body(MockContext())
    assert "nothing to measure" in capsys.readouterr().out


def test_an_unknown_name_is_an_error_not_an_empty_run(tmp_cwd, monkeypatch):
    """A typo must not look like a clean report."""
    _declare(tmp_cwd, _REPO_TASKS_TOML)
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    with pytest.raises(Exit, match=r"entry named 'gamma' in repo-tasks\.toml"):
        consumers.diff.body(MockContext(), name="gamma")


def test_the_report_names_the_version_it_measured_with(tmp_cwd, monkeypatch, capsys):
    """A per-consumer answer only means something against a named version of this package —
    otherwise two rows measured by different tools sit in one table saying nothing."""
    _declare(tmp_cwd, '[[consumer]]\nname = "gone"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    with pytest.raises(Exit):
        consumers.diff.body(MockContext())
    assert "measured with repo-tasks" in capsys.readouterr().out


def test_a_consumer_carrying_the_shipped_configs_reports_up_to_date(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    alpha = _consumer_tree(tmp_cwd, "alpha")
    monkeypatch.setattr(consumers, "_measure", lambda *_: Drift([], [], [], None))
    consumers.diff.body(MockContext())
    assert "alpha: up to date" in capsys.readouterr().out
    assert list(alpha.iterdir()) == [], "read-only: nothing written into the consumer's tree"


def test_a_drifted_consumer_reports_each_kind_of_drift(tmp_cwd, monkeypatch, capsys):
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha")
    drift = Drift(["ruff.toml"], ["pytest-socket"], ["hadolint-py!=2.15.1.2"], None)
    monkeypatch.setattr(consumers, "_measure", lambda *_: drift)
    with pytest.raises(Exit) as excinfo:
        consumers.diff.body(MockContext())
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
        consumers.diff.body(MockContext())
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
        consumers.diff.body(MockContext())
    out = capsys.readouterr().out
    assert "alpha: up to date" in out
    assert "beta: config files behind: pytest.ini" in out


def test_measuring_restores_the_working_directory(tmp_cwd, monkeypatch):
    """`_measure` chdirs into each consumer, so a failure to restore would leave every later task in
    this process reading the wrong tree — and the tasks that write would write there."""
    _declare(tmp_cwd, '[[consumer]]\nname = "alpha"\n')
    monkeypatch.setenv("REPO_TASKS_PROJECTS_ROOT", str(tmp_cwd))
    _consumer_tree(tmp_cwd, "alpha")
    before = Path.cwd()
    with pytest.raises(Exit):
        consumers.diff.body(MockContext())
    assert Path.cwd() == before

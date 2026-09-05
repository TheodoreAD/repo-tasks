"""Tests for repo_tasks.projects: the single-implicit-project fallback run against this repo's own
pyproject.toml, plus workspace-member resolution against throwaway trees built in tmp_path (mirrors
test_quality.py's existing MockContext style, though discover_python_projects doesn't touch c.run).

The workspace cases deliberately build their own minimal tree rather than pointing at this repo's
the real fixture tree — discovery logic gets a fast, minimal case it fully controls (an excluded
member, a
member dir with no pyproject.toml, a table-less root), independent of whatever the dogfood sample
happens to look like."""

from pathlib import Path

import pytest
from invoke import MockContext, Result

from repo_tasks import projects

_ROOT_PYPROJECT = '[project]\nname = "root-pkg"\nversion = "1.0.0"\n'


def _write_member(root: Path, relative: str, name: str, version: str) -> None:
    member = root / relative
    member.mkdir(parents=True)
    (member / "pyproject.toml").write_text(f'[project]\nname = "{name}"\nversion = "{version}"\n')


def _write_workspace_root(root: Path, members: str, exclude: str = "", project: str = _ROOT_PYPROJECT) -> None:
    exclude_line = f"exclude = {exclude}\n" if exclude else ""
    (root / "pyproject.toml").write_text(f"{project}\n[tool.uv.workspace]\nmembers = {members}\n{exclude_line}")


def test_tracked_files_quotes_every_pathspec():
    c = MockContext(run=Result(stdout="a.md\ndocs/b.md\n", exited=0))
    assert projects.tracked_files(c, "*.md", "docs/*.md") == ["a.md", "docs/b.md"]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "git ls-files --cached --others --exclude-standard -- '*.md' 'docs/*.md'",
        hide=True,
        warn=True,
    )


def test_tracked_files_empty_outside_a_git_repo():
    # Every file-gated caller reads an empty list as "nothing to do", which is what keeps
    # shell_check/workflow_check/link_check no-ops instead of hard failures.
    c = MockContext(run=Result(exited=128))
    assert projects.tracked_files(c, "*.md") == []


def test_discover_python_projects_returns_repo_root_first(c):
    """Identity, not version: this asserts the ordering its name describes, and the repo's own
    version is a mutable fact that has no business failing an ordering test. The `pinned_version`
    fixture does not reach here — that patches `version._resolve_project`, and this calls discovery
    directly — so the literal has to go rather than be pinned."""
    root = projects.discover_python_projects(c)[0]
    assert (root.name, root.path) == ("repo-tasks", Path())


def test_discover_python_projects_finds_this_repos_own_dogfood_member(c):
    """This repo is its own workspace consumer — tests/fixtures/sample-service is a real member, and the
    docker image and helm chart in repo-tasks.toml resolve their version group against it."""
    names = [p.name for p in projects.discover_python_projects(c)]
    assert names == ["repo-tasks", "sample-service"]


def test_discover_python_projects_is_empty_without_a_pyproject(c, tmp_cwd):
    assert projects.discover_python_projects(c) == []


def test_discover_python_projects_no_workspace_table_means_root_alone(c, tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text(_ROOT_PYPROJECT)
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="root-pkg", path=Path(), version="1.0.0")
    ]


def test_discover_python_projects_resolves_workspace_member_globs(c, tmp_cwd):
    _write_workspace_root(tmp_cwd, '["examples/*"]')
    _write_member(tmp_cwd, "examples/beta", "beta", "0.2.0")
    _write_member(tmp_cwd, "examples/alpha", "alpha", "0.1.0")
    # Root first, then members sorted — callers index [0] for "the repo's own project".
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="root-pkg", path=Path(), version="1.0.0"),
        projects.PythonProject(name="alpha", path=Path("examples/alpha"), version="0.1.0"),
        projects.PythonProject(name="beta", path=Path("examples/beta"), version="0.2.0"),
    ]


def test_discover_python_projects_honours_workspace_exclude(c, tmp_cwd):
    _write_workspace_root(tmp_cwd, '["examples/*"]', exclude='["examples/skipped"]')
    _write_member(tmp_cwd, "examples/kept", "kept", "0.1.0")
    _write_member(tmp_cwd, "examples/skipped", "skipped", "0.1.0")
    result = projects.discover_python_projects(c)
    assert [p.name for p in result] == ["root-pkg", "kept"]


def test_discover_python_projects_skips_member_dir_without_pyproject(c, tmp_cwd):
    _write_workspace_root(tmp_cwd, '["examples/*"]')
    _write_member(tmp_cwd, "examples/real", "real", "0.1.0")
    (tmp_cwd / "examples" / "not-a-project").mkdir()
    result = projects.discover_python_projects(c)
    assert [p.name for p in result] == ["root-pkg", "real"]


def test_discover_python_projects_allows_a_table_less_workspace_root(c, tmp_cwd):
    """uv's "virtual" workspace root — a pyproject.toml that only groups members, no [project]."""
    _write_workspace_root(tmp_cwd, '["examples/*"]', project="")
    _write_member(tmp_cwd, "examples/only", "only", "0.1.0")
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="only", path=Path("examples/only"), version="0.1.0")
    ]


def test_discover_docker_images_empty_with_no_config_and_no_dockerfile(c, tmp_cwd):
    assert projects.discover_docker_images(c) == []


def test_discover_docker_images_zero_config_default_uses_python_project_name(c, tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text('[project]\nname = "sample-service"\nversion = "1.0.0"\n')
    (tmp_cwd / "Dockerfile").write_text("FROM scratch\n")
    assert projects.discover_docker_images(c) == [
        projects.DockerImage(
            name="sample-service",
            path=Path(),
            dockerfile=Path("Dockerfile"),
            image="sample-service",
            group="sample-service",
        )
    ]


def test_discover_docker_images_zero_config_default_falls_back_to_dirname_without_pyproject(c, tmp_cwd):
    (tmp_cwd / "Dockerfile").write_text("FROM scratch\n")
    result = projects.discover_docker_images(c)
    assert result == [
        projects.DockerImage(
            name=tmp_cwd.name, path=Path(), dockerfile=Path("Dockerfile"), image=tmp_cwd.name, group=tmp_cwd.name
        )
    ]


def test_discover_docker_images_reads_explicit_repo_tasks_toml(c, tmp_cwd):
    (tmp_cwd / "repo-tasks.toml").write_text(
        "[[docker]]\n"
        'name = "sample-service"\n'
        'path = "examples/sample-service"\n'
        'dockerfile = "examples/sample-service/Dockerfile"\n'
        'image = "ghcr.io/org/sample-service"\n'
        'group = "sample-service"\n'
    )
    assert projects.discover_docker_images(c) == [
        projects.DockerImage(
            name="sample-service",
            path=Path("examples/sample-service"),
            dockerfile=Path("examples/sample-service/Dockerfile"),
            image="ghcr.io/org/sample-service",
            group="sample-service",
        )
    ]


def test_discover_docker_images_explicit_entry_group_defaults_to_name(c, tmp_cwd):
    (tmp_cwd / "repo-tasks.toml").write_text(
        '[[docker]]\nname = "solo"\npath = "."\ndockerfile = "Dockerfile"\nimage = "ghcr.io/org/solo"\n'
    )
    result = projects.discover_docker_images(c)
    assert result[0].group == "solo"


def test_discover_helm_charts_empty_with_no_config(c, tmp_cwd):
    assert projects.discover_helm_charts(c) == []


def test_discover_helm_charts_reads_explicit_repo_tasks_toml(c, tmp_cwd):
    (tmp_cwd / "repo-tasks.toml").write_text(
        "[[helm]]\n"
        'name = "sample-service-chart"\n'
        'path = "examples/sample-service/chart"\n'
        'registry = "oci://ghcr.io/org/charts"\n'
        'group = "sample-service"\n'
    )
    assert projects.discover_helm_charts(c) == [
        projects.HelmChart(
            name="sample-service-chart",
            path=Path("examples/sample-service/chart"),
            registry="oci://ghcr.io/org/charts",
            group="sample-service",
        )
    ]


def test_discover_helm_charts_registry_optional_and_group_defaults_to_name(c, tmp_cwd):
    (tmp_cwd / "repo-tasks.toml").write_text('[[helm]]\nname = "solo-chart"\npath = "chart"\n')
    result = projects.discover_helm_charts(c)
    assert result == [projects.HelmChart(name="solo-chart", path=Path("chart"), registry=None, group="solo-chart")]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (">=3.11", "3.11"),
        (">=3.11.2", "3.11"),
        (">=3.12,<4.0", "3.12"),
        ("~=3.13", "3.13"),
        ("==3.14", "3.14"),
        (">= 3.11", "3.11"),
        # An upper bound alone declares no floor — the answer is None, not "4.0".
        ("<4.0", None),
    ],
)
def test_python_floor_reads_the_lower_bound_whichever_operator_states_it(tmp_cwd, spec, expected):
    (tmp_cwd / "pyproject.toml").write_text(f'[project]\nname = "x"\nrequires-python = "{spec}"\n')
    assert projects.python_floor(tmp_cwd) == expected


def test_python_floor_is_none_without_a_requires_python(tmp_cwd):
    (tmp_cwd / "pyproject.toml").write_text('[project]\nname = "x"\n')
    assert projects.python_floor(tmp_cwd) is None


def test_python_floor_is_none_without_a_pyproject(tmp_cwd):
    assert projects.python_floor(tmp_cwd) is None


# ---------------------------------------------------------------------------
# trunk_branch / develop_branch
# ---------------------------------------------------------------------------


def test_branches_default_to_main_and_develop_without_any_config(tmp_cwd):
    """The family convention, and what every consumer following it gets for free — the point of the
    setting is that a repo on a different trunk has something to write, not that everyone must."""
    assert projects.trunk_branch() == "main"
    assert projects.develop_branch() == "develop"


def test_branches_come_from_repo_tasks_toml(tmp_cwd):
    """The case that could not be expressed at all until 2026-09-06: gitflow had `main` as ~20
    string literals, so a repo on `master` had `hotfix_start` branching off a ref that does not
    exist there and no flag to say so."""
    (tmp_cwd / "repo-tasks.toml").write_text('[branches]\ntrunk = "master"\ndevelop = "integration"\n')
    assert projects.trunk_branch() == "master"
    assert projects.develop_branch() == "integration"


def test_one_branch_can_be_set_without_the_other(tmp_cwd):
    (tmp_cwd / "repo-tasks.toml").write_text('[branches]\ntrunk = "master"\n')
    assert projects.trunk_branch() == "master"
    assert projects.develop_branch() == "develop"


@pytest.mark.parametrize(
    "body",
    [
        '[[docker]]\nname = "x"\npath = "."\nimage = "i"\ngroup = "g"\n',  # a real config, no [branches]
        "branches = 1\n",  # the key present but not a table
        "[branches]\ntrunk = 3\n",  # present, wrong type
        '[branches]\ntrunk = ""\n',  # present, empty — a branch name that cannot be checked out
    ],
    ids=["absent", "not-a-table", "wrong-type", "empty"],
)
def test_a_config_that_says_nothing_usable_falls_back(tmp_cwd, body):
    """Falling back beats raising: `repo-tasks.toml` is read by every git-flow-shaped task, so a
    malformed `[branches]` would take out release, hotfix and feature flows at once for a typo in a
    section none of them requires."""
    (tmp_cwd / "repo-tasks.toml").write_text(body)
    assert projects.trunk_branch() == "main"

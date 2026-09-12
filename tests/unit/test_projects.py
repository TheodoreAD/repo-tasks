"""Tests for repo_tasks.projects: the single-implicit-project fallback run against this repo's own
pyproject.toml, plus workspace-member resolution against throwaway trees built in tmp_path (mirrors
test_quality.py's existing MockContext style, though discover_python_projects doesn't touch c.run).

The workspace cases deliberately build their own minimal tree rather than pointing at this repo's
the real fixture tree — discovery logic gets a fast, minimal case it fully controls (an excluded
member, a
member dir with no pyproject.toml, a table-less root), independent of whatever the dogfood sample
happens to look like."""

from collections.abc import Callable
from pathlib import Path

import pytest
from invoke import MockContext, Result

from repo_tasks import projects


@pytest.fixture
def workspace_root(write_pyproject: Callable[..., Path]) -> Callable[..., Path]:
    """A workspace root: the shared `[project]` table plus the `[tool.uv.workspace]` half these
    tests are actually about. `project=False` writes the table-less "virtual" root uv allows, which
    is a shape the shared factory deliberately cannot express."""

    def write(root: Path, members: str, exclude: str = "", project: bool = True) -> Path:
        exclude_line = f"exclude = {exclude}\n" if exclude else ""
        workspace = f"\n[tool.uv.workspace]\nmembers = {members}\n{exclude_line}"
        if not project:
            path = root / "pyproject.toml"
            path.write_text(workspace.lstrip("\n"), encoding="utf-8")
            return path
        return write_pyproject(root, name="root-pkg", version="1.0.0", extra=workspace)

    return write


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


def test_discover_python_projects_no_workspace_table_means_root_alone(c, tmp_cwd, write_pyproject):
    write_pyproject(tmp_cwd, name="root-pkg", version="1.0.0")
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="root-pkg", path=Path(), version="1.0.0")
    ]


def test_discover_python_projects_resolves_workspace_member_globs(c, tmp_cwd, workspace_root, write_pyproject):
    workspace_root(tmp_cwd, '["examples/*"]')
    write_pyproject(tmp_cwd / "examples" / "beta", name="beta", version="0.2.0")
    write_pyproject(tmp_cwd / "examples" / "alpha", name="alpha", version="0.1.0")
    # Root first, then members sorted — callers index [0] for "the repo's own project".
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="root-pkg", path=Path(), version="1.0.0"),
        projects.PythonProject(name="alpha", path=Path("examples/alpha"), version="0.1.0"),
        projects.PythonProject(name="beta", path=Path("examples/beta"), version="0.2.0"),
    ]


def test_discover_python_projects_honours_workspace_exclude(c, tmp_cwd, workspace_root, write_pyproject):
    workspace_root(tmp_cwd, '["examples/*"]', exclude='["examples/skipped"]')
    write_pyproject(tmp_cwd / "examples" / "kept", name="kept", version="0.1.0")
    write_pyproject(tmp_cwd / "examples" / "skipped", name="skipped", version="0.1.0")
    result = projects.discover_python_projects(c)
    assert [p.name for p in result] == ["root-pkg", "kept"]


def test_discover_python_projects_skips_member_dir_without_pyproject(c, tmp_cwd, workspace_root, write_pyproject):
    workspace_root(tmp_cwd, '["examples/*"]')
    write_pyproject(tmp_cwd / "examples" / "real", name="real", version="0.1.0")
    (tmp_cwd / "examples" / "not-a-project").mkdir()
    result = projects.discover_python_projects(c)
    assert [p.name for p in result] == ["root-pkg", "real"]


def test_discover_python_projects_allows_a_table_less_workspace_root(c, tmp_cwd, workspace_root, write_pyproject):
    """uv's "virtual" workspace root — a pyproject.toml that only groups members, no [project]."""
    workspace_root(tmp_cwd, '["examples/*"]', project=False)
    write_pyproject(tmp_cwd / "examples" / "only", name="only", version="0.1.0")
    assert projects.discover_python_projects(c) == [
        projects.PythonProject(name="only", path=Path("examples/only"), version="0.1.0")
    ]


def test_discover_docker_images_empty_with_no_config_and_no_dockerfile(c, tmp_cwd):
    assert projects.discover_docker_images(c) == []


def test_discover_docker_images_zero_config_default_uses_python_project_name(c, tmp_cwd, write_pyproject):
    write_pyproject(tmp_cwd, name="sample-service", version="1.0.0")
    (tmp_cwd / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
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
    (tmp_cwd / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
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
        'group = "sample-service"\n',
        encoding="utf-8",
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
        '[[docker]]\nname = "solo"\npath = "."\ndockerfile = "Dockerfile"\nimage = "ghcr.io/org/solo"\n',
        encoding="utf-8",
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
        'group = "sample-service"\n',
        encoding="utf-8",
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
    (tmp_cwd / "repo-tasks.toml").write_text('[[helm]]\nname = "solo-chart"\npath = "chart"\n', encoding="utf-8")
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
def test_python_floor_reads_the_lower_bound_whichever_operator_states_it(tmp_cwd, write_pyproject, spec, expected):
    write_pyproject(tmp_cwd, version=None, requires_python=spec)
    assert projects.python_floor(tmp_cwd) == expected


def test_python_floor_is_none_without_a_requires_python(tmp_cwd, write_pyproject):
    write_pyproject(tmp_cwd, version=None)
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
    (tmp_cwd / "repo-tasks.toml").write_text(
        '[branches]\ntrunk = "master"\ndevelop = "integration"\n', encoding="utf-8"
    )
    assert projects.trunk_branch() == "master"
    assert projects.develop_branch() == "integration"


def test_one_branch_can_be_set_without_the_other(tmp_cwd):
    (tmp_cwd / "repo-tasks.toml").write_text('[branches]\ntrunk = "master"\n', encoding="utf-8")
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
    (tmp_cwd / "repo-tasks.toml").write_text(body, encoding="utf-8")
    assert projects.trunk_branch() == "main"


def test_discover_python_projects_names_the_file_when_a_version_is_dynamic(c, tmp_cwd, write_pyproject):
    """`dynamic = ["version"]` is the realistic way to reach this: hatch-vcs and setuptools-scm
    derive the version from git, and this package's model is a static field it rewrites. It raised
    before this — with a bare `KeyError: 'version'` naming neither the file nor the reason."""
    write_pyproject(tmp_cwd, version=None, extra='dynamic = ["version"]\n')
    with pytest.raises(ValueError, match=r"pyproject.toml: \[project\] declares no version") as exc_info:
        projects.discover_python_projects(c)
    assert "dynamic" in str(exc_info.value)


def test_discover_python_projects_names_the_incomplete_member(c, tmp_cwd, workspace_root, write_pyproject):
    # The half a KeyError could not answer: which of a workspace's pyproject.toml files it was.
    workspace_root(tmp_cwd, '["members/*"]')
    write_pyproject(tmp_cwd / "members" / "svc", name="svc", version=None)
    with pytest.raises(ValueError, match=r"members/svc/pyproject.toml"):
        projects.discover_python_projects(c)


@pytest.mark.parametrize("table", ["docker", "helm"])
def test_discovery_names_the_manifest_entry_missing_a_required_key(c, tmp_cwd, table):
    # repo-tasks.toml is hand-authored, so a missing key is an ordinary typo rather than a bug.
    (tmp_cwd / "repo-tasks.toml").write_text(f'[[{table}]]\nname = "svc"\n', encoding="utf-8")
    discover = projects.discover_docker_images if table == "docker" else projects.discover_helm_charts
    with pytest.raises(ValueError, match=rf"repo-tasks.toml: a \[\[{table}\]\] entry declares no path"):
        discover(c)


def test_current_branch_reads_the_checkouts_own_head():
    # The one git question both branching models ask, and asked the same way by each of them
    # before it moved here.
    c = MockContext(run=Result(stdout="release/1.2.0\n", exited=0))
    assert projects.current_branch(c) == "release/1.2.0"
    c.run.assert_called_once_with("git rev-parse --abbrev-ref HEAD", hide=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_docs_generators_reads_the_declared_commands(tmp_path):
    (tmp_path / "repo-tasks.toml").write_text(
        '[docs]\ngenerators = ["inv devcontainer.render-docs", "inv screenshot.render-docs"]\n',
        encoding="utf-8",
    )
    assert projects.docs_generators(tmp_path) == ["inv devcontainer.render-docs", "inv screenshot.render-docs"]


def test_docs_generators_is_empty_without_config(tmp_path):
    # Every consumer that generates nothing, and this repo: no file at all.
    assert projects.docs_generators(tmp_path) == []


def test_docs_generators_is_empty_when_the_config_declares_none(tmp_path):
    # A repo-tasks.toml that exists for some other reason -- docker images, branch names -- says
    # nothing about docs, and must not be read as declaring an empty generator it then runs.
    (tmp_path / "repo-tasks.toml").write_text('[branches]\ntrunk = "master"\n', encoding="utf-8")
    assert projects.docs_generators(tmp_path) == []

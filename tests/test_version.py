"""Tests for repo_tasks.version: dedicated coverage for _bumpversion_config (the one piece of real
logic — the per-group config bump-my-version actually reads) plus bump's overall command shape,
following test_quality.py's existing MockContext style."""

from pathlib import Path

import pytest
from invoke import MockContext

from repo_tasks import projects, version


def test_bumpversion_config_targets_the_project_pyproject_and_current_version():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, tag=True)  # pyright: ignore[reportPrivateUsage] — testing the one piece of real logic directly
    assert 'current_version = "0.1.0"' in config
    assert 'filename = "pyproject.toml"' in config
    assert 'tag_name = "v{new_version}"' in config


def test_bumpversion_config_omits_tag_when_tag_is_false():
    project = projects.PythonProject(name="sample", path=Path(), version="0.1.0")
    config = version._bumpversion_config(project, tag=False)  # pyright: ignore[reportPrivateUsage]
    assert "tag = false" in config
    assert "tag_name" not in config


def test_bump_invokes_bumpversion_with_a_generated_config_file_and_returns_new_version():
    c = MockContext(run=True)
    result = version.bump.body(c, part="minor")  # pyright: ignore[reportAny, reportFunctionMemberAccess]

    call_args = c.run.call_args_list[0]  # pyright: ignore[reportAttributeAccessIssue]
    command = call_args[0][0]
    assert command.startswith("bump-my-version bump minor --config-file ")
    assert call_args[1] == {"echo": True}

    config_path = Path(command.removeprefix("bump-my-version bump minor --config-file "))
    assert not config_path.exists()  # cleaned up after the run

    assert result == "0.1.0"  # MockContext never really runs bump-my-version, so the file is unchanged


def test_bump_raises_for_an_unknown_group():
    c = MockContext(run=True)
    with pytest.raises(ValueError, match="no-such-project"):
        version.bump.body(c, part="minor", group="no-such-project")  # pyright: ignore[reportAny, reportFunctionMemberAccess]

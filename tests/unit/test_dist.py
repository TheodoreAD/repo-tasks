"""Tests for repo_tasks.dist: command-string construction for clean/build/publish (MockContext,
matching tests/test_quality.py's style), plus versions' JSON/HTML parsing — network-free via
monkeypatching the module's own _get and discover_python_projects."""

import json
import urllib.error
from types import SimpleNamespace

import pytest

from repo_tasks import dist


def _stub_project(name="repo-tasks", version="1.2.3"):
    return lambda c: [SimpleNamespace(name=name, version=version)]


def _stub_workspace():
    """A root project plus one workspace member, root first — projects.py's own ordering."""
    return lambda c: [
        SimpleNamespace(name="repo-tasks", version="1.2.3"),
        SimpleNamespace(name="sample-service", version="1.2.3"),
    ]


def test_clean_noop_when_dist_absent(c, tmp_cwd, capsys):
    dist.clean.body(c)
    assert "nothing to clean" in capsys.readouterr().out


def test_clean_removes_dist_dir(c, tmp_cwd):
    (tmp_cwd / "dist").mkdir()
    dist.clean.body(c)
    assert not (tmp_cwd / "dist").exists()


@pytest.mark.parametrize("task_name", ["build", "publish", "list_versions"])
def test_tasks_no_op_cleanly_with_no_python_project(c, tmp_cwd, monkeypatch, capsys, task_name):
    monkeypatch.setattr(dist, "discover_python_projects", lambda c: [])
    getattr(dist, task_name).body(c)  # pyright: ignore[reportAny]
    c.run.assert_not_called()
    assert "nothing to do" in capsys.readouterr().out


def test_explicit_project_still_errors_with_no_python_project(c, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", lambda c: [])
    with pytest.raises(ValueError, match="nonexistent"):
        dist.build.body(c, project="nonexistent")


def test_build_default_is_wheel_only(c, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    dist.build.body(c)
    c.run.assert_called_once_with("uv build --wheel --package repo-tasks", echo=True)


def test_build_sdist(c, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    dist.build.body(c, sdist=True)
    c.run.assert_called_once_with("uv build --package repo-tasks", echo=True)


def test_build_project_selects_a_workspace_member(c, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_workspace())
    dist.build.body(c, project="sample-service")
    c.run.assert_called_once_with("uv build --wheel --package sample-service", echo=True)


def test_build_unknown_project_raises(c, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_workspace())
    with pytest.raises(ValueError, match="no python project found for 'nope'"):
        dist.build.body(c, project="nope")


def test_publish_default(c, tmp_cwd, monkeypatch):
    # tmp_cwd, not tmp_path: publish cleans dist/ from its own body, so this must never run
    # against the real repo.
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    dist.publish.body(c)
    assert [call.args[0] for call in c.run.call_args_list] == [
        "uv build --wheel --package repo-tasks",
        "uv publish",
    ]


def test_publish_with_index_and_dry_run(c, tmp_cwd, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    dist.publish.body(c, index="https://test.pypi.org/legacy/", dry_run=True)
    assert c.run.call_args_list[-1].args[0] == ("uv publish --index https://test.pypi.org/legacy/ --dry-run")


def test_publish_refuses_a_dev_build_without_a_named_index(c, tmp_cwd, monkeypatch):
    # PyPI rejects local versions (+gHASH) outright; say so before building rather than at upload.
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project(version="1.2.4.dev5+gabc1234"))
    with pytest.raises(ValueError, match="dev build"):
        dist.publish.body(c)
    c.run.assert_not_called()


def test_publish_dev_build_to_a_named_index(c, tmp_cwd, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project(version="1.2.4.dev5+gabc1234"))
    dist.publish.body(c, index="devpi")
    assert c.run.call_args_list[-1].args[0] == "uv publish --index devpi"


def test_build_dev_rewrites_the_version_before_building(c, monkeypatch):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    seen = []
    monkeypatch.setattr(dist, "set_dev", lambda c, group=None: seen.append(group))
    dist.build.body(c, dev=True)
    assert seen == ["repo-tasks"]
    c.run.assert_called_once_with("uv build --wheel --package repo-tasks", echo=True)


def test_publish_builds_the_named_member_not_the_root(c, tmp_cwd, monkeypatch):
    """The reason publish builds from its own body instead of pre=[build]: invoke's pre-tasks take
    no caller arguments, so --project would have silently published the root project's wheel."""
    monkeypatch.setattr(dist, "discover_python_projects", _stub_workspace())
    dist.publish.body(c, project="sample-service")
    assert [call.args[0] for call in c.run.call_args_list] == [
        "uv build --wheel --package sample-service",
        "uv publish",
    ]


def test_versions_prints_from_json_versions_key(c, monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    payload = json.dumps({"versions": ["2.0", "1.0", "1.10"]})
    monkeypatch.setattr(dist, "_get", lambda url, accept=None: payload.encode())
    dist.list_versions.body(c)
    assert capsys.readouterr().out.splitlines() == ["1.0", "1.10", "2.0"]


def test_versions_derives_from_json_files_when_versions_key_absent(c, monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    files = [{"filename": "x-1.0.whl", "version": "1.0"}, {"filename": "x-2.0.whl", "version": "2.0"}]
    payload = json.dumps({"files": files})
    monkeypatch.setattr(dist, "_get", lambda url, accept=None: payload.encode())
    dist.list_versions.body(c)
    assert capsys.readouterr().out.splitlines() == ["1.0", "2.0"]


def test_versions_derives_from_json_filename_when_version_key_absent(c, monkeypatch, capsys):
    # Real-world gap found against devpi: PEP 691's per-file "version" key is optional and devpi
    # omits it entirely — the version must come from the filename instead.
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project("repo-tasks"))
    files = [{"filename": "repo_tasks-1.0.0-py3-none-any.whl"}, {"filename": "repo_tasks-2.0.0.tar.gz"}]
    payload = json.dumps({"files": files})
    monkeypatch.setattr(dist, "_get", lambda url, accept=None: payload.encode())
    dist.list_versions.body(c)
    assert capsys.readouterr().out.splitlines() == ["1.0.0", "2.0.0"]


def test_versions_falls_back_to_html_when_json_unavailable(c, monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())

    def fake_get(url, accept=None):
        if accept == dist._JSON_ACCEPT:
            raise urllib.error.URLError("no json support")
        html = (
            '<a href="../../packages/aa/repo_tasks-1.0.0-py3-none-any.whl">repo_tasks-1.0.0-py3-none-any.whl</a>\n'
            '<a href="../../packages/bb/repo_tasks-2.0.0.tar.gz">repo_tasks-2.0.0.tar.gz</a>\n'
        )
        return html.encode()

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.list_versions.body(c)
    assert capsys.readouterr().out.splitlines() == ["1.0.0", "2.0.0"]


def test_versions_html_fallback_strips_sha256_fragment(c, monkeypatch, capsys):
    # Real-world gap found against devpi: real PEP 503 indices append #sha256=... to hrefs — the
    # regex must stop at '#', or the captured "filename" never matches _version_from_filename.
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project("repo-tasks"))

    def fake_get(url, accept=None):
        if accept == dist._JSON_ACCEPT:
            raise urllib.error.URLError("no json support")
        html = (
            '<a href="../../+f/aa/repo_tasks-1.0.0-py3-none-any.whl#sha256=abc123">'
            "repo_tasks-1.0.0-py3-none-any.whl</a>\n"
        )
        return html.encode()

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.list_versions.body(c)
    assert capsys.readouterr().out.splitlines() == ["1.0.0"]


def test_versions_no_releases_found_on_404(c, monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())

    def fake_get(url, accept=None):
        raise dist._NotFoundError

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.list_versions.body(c)
    assert "no releases found" in capsys.readouterr().out


def test_versions_no_releases_found_after_html_404(c, monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())

    def fake_get(url, accept=None):
        if accept == dist._JSON_ACCEPT:
            raise urllib.error.URLError("no json support")
        raise dist._NotFoundError

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.list_versions.body(c)
    assert "no releases found" in capsys.readouterr().out


def test_normalize_project_name():
    assert dist._normalize("Repo_Tasks.Extra") == "repo-tasks-extra"


def test_version_from_filename_wheel():
    assert dist._version_from_filename("repo_tasks-1.2.3-py3-none-any.whl", "repo-tasks") == "1.2.3"


def test_version_from_filename_sdist():
    assert dist._version_from_filename("repo_tasks-1.2.3.tar.gz", "repo-tasks") == "1.2.3"


def test_version_from_filename_unrecognized_extension():
    assert dist._version_from_filename("repo_tasks-1.2.3.exe", "repo-tasks") is None

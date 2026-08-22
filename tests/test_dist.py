"""Tests for repo_tasks.dist: command-string construction for clean/build/publish (MockContext,
matching tests/test_quality.py's style), plus versions' JSON/HTML parsing — network-free via
monkeypatching the module's own _get and discover_python_projects."""

import json
import urllib.error
from types import SimpleNamespace

from invoke import MockContext

from repo_tasks import dist


def _stub_project(name="repo-tasks"):
    return lambda c: [SimpleNamespace(name=name)]


def test_clean_noop_when_dist_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    c = MockContext()
    dist.clean.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "nothing to clean" in capsys.readouterr().out


def test_clean_removes_dist_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dist").mkdir()
    c = MockContext()
    dist.clean.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert not (tmp_path / "dist").exists()


def test_build_default_is_wheel_only():
    c = MockContext(run=True)
    dist.build.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv build --wheel", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_build_sdist():
    c = MockContext(run=True)
    dist.build.body(c, sdist=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv build", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_publish_default():
    c = MockContext(run=True)
    dist.publish.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv publish", echo=True)  # pyright: ignore[reportAttributeAccessIssue]


def test_publish_with_index_and_dry_run():
    c = MockContext(run=True)
    dist.publish.body(c, index="https://test.pypi.org/legacy/", dry_run=True)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(  # pyright: ignore[reportAttributeAccessIssue]
        "uv publish --index https://test.pypi.org/legacy/ --dry-run", echo=True
    )


def test_versions_prints_from_json_versions_key(monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    payload = json.dumps({"versions": ["2.0", "1.0", "1.10"]})
    monkeypatch.setattr(dist, "_get", lambda url, accept=None: payload.encode())
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.splitlines() == ["1.0", "1.10", "2.0"]


def test_versions_derives_from_json_files_when_versions_key_absent(monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())
    files = [{"filename": "x-1.0.whl", "version": "1.0"}, {"filename": "x-2.0.whl", "version": "2.0"}]
    payload = json.dumps({"files": files})
    monkeypatch.setattr(dist, "_get", lambda url, accept=None: payload.encode())
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.splitlines() == ["1.0", "2.0"]


def test_versions_derives_from_json_filename_when_version_key_absent(monkeypatch, capsys):
    # Real-world gap found against devpi: PEP 691's per-file "version" key is optional and devpi
    # omits it entirely — the version must come from the filename instead.
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project("repo-tasks"))
    files = [{"filename": "repo_tasks-1.0.0-py3-none-any.whl"}, {"filename": "repo_tasks-2.0.0.tar.gz"}]
    payload = json.dumps({"files": files})
    monkeypatch.setattr(dist, "_get", lambda url, accept=None: payload.encode())
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.splitlines() == ["1.0.0", "2.0.0"]


def test_versions_falls_back_to_html_when_json_unavailable(monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())

    def fake_get(url, accept=None):
        if accept == dist._JSON_ACCEPT:  # pyright: ignore[reportPrivateUsage]
            raise urllib.error.URLError("no json support")
        html = (
            '<a href="../../packages/aa/repo_tasks-1.0.0-py3-none-any.whl">repo_tasks-1.0.0-py3-none-any.whl</a>\n'
            '<a href="../../packages/bb/repo_tasks-2.0.0.tar.gz">repo_tasks-2.0.0.tar.gz</a>\n'
        )
        return html.encode()

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.splitlines() == ["1.0.0", "2.0.0"]


def test_versions_html_fallback_strips_sha256_fragment(monkeypatch, capsys):
    # Real-world gap found against devpi: real PEP 503 indices append #sha256=... to hrefs — the
    # regex must stop at '#', or the captured "filename" never matches _version_from_filename.
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project("repo-tasks"))

    def fake_get(url, accept=None):
        if accept == dist._JSON_ACCEPT:  # pyright: ignore[reportPrivateUsage]
            raise urllib.error.URLError("no json support")
        html = (
            '<a href="../../+f/aa/repo_tasks-1.0.0-py3-none-any.whl#sha256=abc123">'
            "repo_tasks-1.0.0-py3-none-any.whl</a>\n"
        )
        return html.encode()

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert capsys.readouterr().out.splitlines() == ["1.0.0"]


def test_versions_no_releases_found_on_404(monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())

    def fake_get(url, accept=None):
        raise dist._NotFoundError  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "no releases found" in capsys.readouterr().out


def test_versions_no_releases_found_after_html_404(monkeypatch, capsys):
    monkeypatch.setattr(dist, "discover_python_projects", _stub_project())

    def fake_get(url, accept=None):
        if accept == dist._JSON_ACCEPT:  # pyright: ignore[reportPrivateUsage]
            raise urllib.error.URLError("no json support")
        raise dist._NotFoundError  # pyright: ignore[reportPrivateUsage]

    monkeypatch.setattr(dist, "_get", fake_get)
    dist.versions.body(MockContext())  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert "no releases found" in capsys.readouterr().out


def test_normalize_project_name():
    assert dist._normalize("Repo_Tasks.Extra") == "repo-tasks-extra"  # pyright: ignore[reportPrivateUsage]


def test_version_from_filename_wheel():
    assert dist._version_from_filename("repo_tasks-1.2.3-py3-none-any.whl", "repo-tasks") == "1.2.3"  # pyright: ignore[reportPrivateUsage]


def test_version_from_filename_sdist():
    assert dist._version_from_filename("repo_tasks-1.2.3.tar.gz", "repo-tasks") == "1.2.3"  # pyright: ignore[reportPrivateUsage]


def test_version_from_filename_unrecognized_extension():
    assert dist._version_from_filename("repo_tasks-1.2.3.exe", "repo-tasks") is None  # pyright: ignore[reportPrivateUsage]

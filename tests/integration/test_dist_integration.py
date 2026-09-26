"""Real, non-mocked round trips for repo_tasks.dist — nothing here is stubbed at the Python level,
so this is the tier that caught dist.py's two real parsing gaps (see tests/unit/test_dist.py's
test_versions_derives_from_json_filename_when_version_key_absent and
test_versions_html_fallback_strips_sha256_fragment).

Two servers, because no one lightweight server does both halves (see conftest.py's package_index
and json_index, and contributing/test-tiers.md):

- `package_index` is a real pypiserver: the build is published to it by a real `uv publish` and read
  back through dist.list_versions' PEP 503 HTML branch, sha256 fragments and all.
- `json_index` is a stub serving PEP 691, which no lightweight real index does. It is still a real
  socket round trip, which is what separates these from the unit tier's mocked `_get`.
"""

import pytest
from invoke import Exit

from repo_tasks import dist
from repo_tasks.projects import discover_python_projects


@pytest.fixture(autouse=True)
def _clean_dist(c):
    yield
    dist.clean.body(c)


def _build_and_publish(c, package_index) -> None:
    dist.build.body(c)
    c.run(
        f"uv publish --publish-url {package_index.upload_url} "
        f"-u '{package_index.username}' -p '{package_index.password}' dist/*",
        echo=True,
    )


def test_versions_html_fallback_round_trip(c, package_index):
    """The real half: a real upload, then the HTML branch parsed off a real index's real response."""
    _build_and_publish(c, package_index)

    project = discover_python_projects(c)[0]
    normalized = dist._normalize(project.name)
    url = f"{package_index.simple_url.rstrip('/')}/{normalized}/"

    # No accept header at all, exactly what versions() sends on its HTML-fallback branch.
    found = dist._html_versions(dist._get(url), normalized)

    assert project.version in found


def test_versions_falls_back_to_html_because_the_index_serves_no_json(c, package_index, capsys):
    """The fallback is exercised end to end, through list_versions rather than its helpers.

    pypiserver ignores the JSON Accept header and answers HTML, which is precisely the condition the
    fallback exists for — so this asserts the *whole* task does the right thing against an index
    that speaks only PEP 503, not merely that the parser works.
    """
    _build_and_publish(c, package_index)
    capsys.readouterr()  # drain build/publish's own echoed output

    dist.list_versions.body(c, index=package_index.simple_url)

    project = discover_python_projects(c)[0]
    assert capsys.readouterr().out.splitlines() == [project.version]


@pytest.mark.parametrize(
    ("label", "payload", "expected"),
    [
        # PyPI's own shape, measured 2026-08-30: a top-level `versions` key, and no per-file
        # `version` key at all. list_versions returns on the first sub-path.
        ("top-level versions key", {"versions": ["1.0.0", "2.0.0"]}, ["1.0.0", "2.0.0"]),
        # The sub-path nothing real emits — neither PyPI nor devpi — so it was mock-only before.
        (
            "per-file version key",
            {"files": [{"filename": "repo_tasks-1.0.0-py3-none-any.whl", "version": "1.0.0"}]},
            ["1.0.0"],
        ),
        # devpi's old shape: neither key, so the version comes from the filename. This is the
        # sub-path that carried the original bug.
        (
            "filename derivation",
            {"files": [{"filename": "repo_tasks-3.1.4-py3-none-any.whl"}, {"filename": "repo_tasks-2.0.0.tar.gz"}]},
            ["2.0.0", "3.1.4"],
        ),
    ],
)
def test_versions_json_sub_paths_over_a_real_socket(c, json_index, capsys, label, payload, expected):
    url = json_index.serve(payload)
    capsys.readouterr()

    dist.list_versions.body(c, index=url)

    assert capsys.readouterr().out.splitlines() == expected, label
    # The point of doing this over a socket rather than with a mocked _get: prove the media type
    # was actually sent. A mock can only show that _get was called with it.
    assert json_index.seen_accept == [dist._JSON_ACCEPT], label


def _write_monorepo(root) -> None:
    """The coupling-checker plan's fixture, generated rather than committed so this repo's own lock
    never has to resolve it: three members, one declared edge, one undeclared, no third-party
    dependencies, so nothing beyond the build backend is fetched."""
    member = """\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [{deps}]
{sources}
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/{module}"]
"""
    files = {
        "pyproject.toml": (
            '[project]\nname = "monorepo"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
            'dependencies = []\n\n[tool.uv]\npackage = false\n\n[tool.uv.workspace]\nmembers = ["packages/*"]\n'
        ),
        "packages/pkg-core/pyproject.toml": member.format(name="pkg-core", deps="", sources="", module="pkg_core"),
        "packages/pkg-core/src/pkg_core/__init__.py": "VALUE = 'core'\n",
        "packages/pkg-api/pyproject.toml": member.format(
            name="pkg-api",
            deps='"pkg-core"',
            sources="\n[tool.uv.sources]\npkg-core = { workspace = true }\n",
            module="pkg_api",
        ),
        "packages/pkg-api/src/pkg_api/__init__.py": "from pkg_core import VALUE\n",
        "packages/pkg-worker/pyproject.toml": member.format(
            name="pkg-worker", deps="", sources="", module="pkg_worker"
        ),
        "packages/pkg-worker/src/pkg_worker/__init__.py": "from pkg_core import VALUE\n",
    }
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_check_isolated_catches_an_undeclared_sibling_import(c, tmp_path, monkeypatch, capsys):
    """The ground truth the task stands on, end to end: the undeclared edge imports in the shared
    workspace and fails alone, while the declared one passes both ways."""
    _write_monorepo(tmp_path)
    monkeypatch.chdir(tmp_path)
    c.run("uv lock --quiet", env={"VIRTUAL_ENV": ""})
    with pytest.raises(Exit):
        dist.check_isolated.body(c)
    out = capsys.readouterr().out
    assert "monorepo  installs nothing (a virtual project) — skipped" in out
    assert "pkg-api  imports alone (pkg_api)" in out
    assert "pkg-core  imports alone (pkg_core)" in out
    assert "pkg-worker  FAILS alone — ModuleNotFoundError: No module named 'pkg_core'" in out

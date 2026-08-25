"""Real, non-mocked round trip for repo_tasks.dist against a local devpi-server (see conftest.py's
devpi_index fixture): build the real wheel, publish it for real, then query it back through both of
dist.list_versions' code paths (PEP 691 JSON and the PEP 503 HTML fallback) — unlike tests/test_dist.py's
unit tests, nothing here is mocked, so this is what actually caught dist.py's two real parsing gaps
(see tests/test_dist.py's test_versions_derives_from_json_filename_when_version_key_absent and
test_versions_html_fallback_strips_sha256_fragment)."""

import pytest

from repo_tasks import dist
from repo_tasks.projects import discover_python_projects


@pytest.fixture(autouse=True)
def _clean_dist(c):
    yield
    dist.clean.body(c)


def _build_and_publish(c, devpi_index) -> None:
    dist.build.body(c)
    c.run(
        f"uv publish --publish-url {devpi_index.upload_url} -u {devpi_index.username} -p {devpi_index.password} dist/*",
        echo=True,
    )


def test_versions_json_round_trip(c, devpi_index, capsys):
    _build_and_publish(c, devpi_index)
    capsys.readouterr()  # drain build/publish's own echoed output

    dist.list_versions.body(c, index=devpi_index.simple_url)

    project = discover_python_projects(c)[0]
    assert capsys.readouterr().out.splitlines() == [project.version]


def test_versions_html_fallback_round_trip(c, devpi_index):
    _build_and_publish(c, devpi_index)

    project = discover_python_projects(c)[0]
    normalized = dist._normalize(project.name)
    url = f"{devpi_index.simple_url.rstrip('/')}/{normalized}/"

    # No accept header at all, exactly what versions() sends on its HTML-fallback branch.
    found = dist._html_versions(dist._get(url), normalized)

    assert project.version in found

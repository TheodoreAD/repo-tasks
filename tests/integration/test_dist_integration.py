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

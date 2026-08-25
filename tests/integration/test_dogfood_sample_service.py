"""The dogfood round trip: this repo's own tests/fixtures/sample-service, built and pushed through
repo_tasks' own docker and helm tasks against a real (local) registry, then read back.

Distinct from test_docker_integration.py, which proves docker.build/push work at all using a
throwaway `FROM scratch` image. This module runs them against the real multi-stage Dockerfile a
consumer would actually write — plus helm lint/package/push on the chart that wraps it — so a
regression in the recipe README documents, or in the shared version group tying image tag to chart
appVersion, fails here rather than in someone's deploy.

Everything runs from the repo root rather than tmp_path: the artifacts under test are this repo's
own committed files, resolved through the same repo-tasks.toml a developer's `inv` call resolves.
The published-artifact fixtures are module-scoped and follow clean_os_container's pattern (their
own Context and pytest.MonkeyPatch, since a module-scoped fixture can't take the function-scoped
ones), so the build and the push happen once for the module instead of per test.
"""

import http.client
import json
import subprocess
import tarfile
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from invoke import Config, Context

from repo_tasks import docker as docker_tasks
from repo_tasks import helm as helm_tasks
from repo_tasks.projects import discover_docker_images, discover_helm_charts, discover_python_projects

_REPO_ROOT = Path(__file__).parent.parent.parent
_SERVICE = "sample-service"
_VERSION_PROBE = "from importlib.metadata import version; print(version('sample-service'))"


def _registry_tags(registry: str, repository: str) -> list[str]:
    url = f"http://{registry}/v2/{repository}/tags/list"
    with cast(http.client.HTTPResponse, urllib.request.urlopen(url)) as response:
        payload = cast(dict[str, object], json.loads(response.read()))
    return cast(list[str], payload["tags"])


def _repo_context() -> Context:
    """A real Context with the repo root as cwd, for the module-scoped fixtures. Same in_stream
    disabling as conftest's `c` fixture, for the same reason."""
    return Context(config=Config(overrides={"run": {"in_stream": False}}))


@pytest.fixture(scope="module", autouse=True)
def _repo_root_cwd():
    """Discovery reads repo-tasks.toml/pyproject.toml relative to cwd, and docker.build's context
    is a relative path — pin cwd for the module rather than assuming pytest was invoked from the
    repo root."""
    mp = pytest.MonkeyPatch()
    mp.chdir(_REPO_ROOT)
    yield
    mp.undo()


@pytest.fixture(scope="module")
def service_version():
    return next(p.version for p in discover_python_projects(_repo_context()) if p.name == _SERVICE)


@pytest.fixture(scope="module")
def pushed_image(docker_registry):
    """The real sample-service image, released (build -> tag latest -> push both) to the local
    registry through docker.release itself. Only the image *ref* is redirected at the local
    registry; the Dockerfile, context, and version group all come from the committed
    repo-tasks.toml."""
    image = next(i for i in discover_docker_images(_repo_context()) if i.name == _SERVICE)
    local = replace(image, image=f"{docker_registry}/{_SERVICE}")
    mp = pytest.MonkeyPatch()
    mp.setattr(docker_tasks, "discover_docker_images", lambda c: [local])
    try:
        docker_tasks.release.body(_repo_context())
    finally:
        mp.undo()
    return local.image


@pytest.fixture(scope="module")
def pushed_chart(docker_registry):
    """The real chart, linted, packaged, and pushed to the same local registry through helm.py's
    own tasks. --plain-http because helm has no equivalent of docker's automatic loopback
    insecure-registry exemption and would otherwise speak HTTPS to it."""
    ctx = _repo_context()
    helm_tasks.lint.body(ctx)
    helm_tasks.package.body(ctx)
    helm_tasks.push.body(ctx, registry=f"oci://{docker_registry}/charts", plain_http=True)
    return f"charts/{_SERVICE}"


def test_the_sample_service_is_one_group_across_image_and_chart():
    """The whole point of the pairing: one group, so one bump moves image tag and chart together."""
    image = next(i for i in discover_docker_images(_repo_context()) if i.name == _SERVICE)
    chart = next(ch for ch in discover_helm_charts(_repo_context()) if ch.name == _SERVICE)
    assert image.group == chart.group == _SERVICE


def test_docker_release_pushes_the_group_version_and_latest(docker_registry, pushed_image, service_version):
    assert sorted(_registry_tags(docker_registry, _SERVICE)) == sorted([service_version, "latest"])


def test_the_pushed_image_runs_the_wheel_that_was_built_for_it(docker_registry, pushed_image, service_version):
    """Not just "an image exists": the container really runs the wheel dist.build produced and
    reports the version from its installed metadata, not from any constant in the source tree."""
    ref = f"{pushed_image}:{service_version}"
    subprocess.run(["docker", "pull", ref], check=True, capture_output=True)
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python", ref, "-c", _VERSION_PROBE],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == service_version


def test_the_image_runs_as_a_non_root_user(docker_registry, pushed_image, service_version):
    result = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "id", f"{pushed_image}:{service_version}", "-u"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() != "0"


def test_helm_push_lands_the_chart_at_its_group_version(docker_registry, pushed_chart, service_version):
    assert _registry_tags(docker_registry, pushed_chart) == [service_version]


def test_the_source_chart_keeps_the_quoting_the_group_bump_searches_for(service_version, sample_chart_dir):
    """version.py's generated bump-my-version config searches for a quoted `appVersion:` and an
    unquoted `version:` literally, and bump-my-version fails on a search string it cannot find.
    Anything that reformats this file — a YAML formatter, an editor's "normalize quotes" — breaks
    the group bump, so pin the exact shapes here rather than only in the generated-config test."""
    chart_yaml = (sample_chart_dir / "Chart.yaml").read_text()
    assert f"version: {service_version}\n" in chart_yaml
    assert f'appVersion: "{service_version}"' in chart_yaml


def test_the_packaged_chart_deploys_the_tag_docker_release_pushed(pushed_chart, service_version, sample_chart_dir):
    """The pairing's actual payload: appVersion is what the chart renders as the image tag, and
    the shared version group is what keeps it equal to the tag docker.release pushed."""
    archive = _REPO_ROOT / "dist" / "helm" / f"{_SERVICE}-{service_version}.tgz"
    with tarfile.open(archive) as tar:
        member = tar.extractfile(f"{_SERVICE}/Chart.yaml")
        assert member is not None
        # `helm package` re-serializes Chart.yaml through its own YAML marshaller: comments are
        # gone and appVersion comes back unquoted. Match on the value, never on the source file's
        # formatting — that belongs to the test above, against the source file itself.
        packaged = member.read().decode()
    assert f"appVersion: {service_version}\n" in packaged

    rendered = subprocess.run(
        ["helm", "template", "probe", str(sample_chart_dir)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f'image: "ghcr.io/theodoread/{_SERVICE}:{service_version}"' in rendered

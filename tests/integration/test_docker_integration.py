"""Real, non-mocked round trip for repo_tasks.docker against a local registry:3 container (see
conftest.py's docker_registry fixture): build and push a throwaway image, then confirm the pushed
tag is actually queryable back from the registry's own API — unlike tests/test_docker.py's unit
tests, this exercises real `docker build`/`docker push` against a real (if local) registry.

`docker.check` is exercised here too, for the same reason it is not a gate step: BuildKit's checks
resolve base-image metadata and evaluate the build graph, so they need a daemon and the network
behind it. hadolint covers the static half in `quality.dockerfile-check`."""

import http.client
import json
import urllib.request
from typing import cast

import pytest
from invoke import UnexpectedExit

from repo_tasks import docker
from repo_tasks.projects import DockerImage


@pytest.mark.smoke
def test_check_passes_for_this_repos_own_images(c):
    """Real discovery, real daemon, no mocks — `inv docker.check` against whatever repo-tasks.toml
    declares. Deliberately not `--project`-narrowed: the point is that every image this repo
    actually ships is clean under BuildKit's own checks."""
    docker.check.body(c)


def test_check_fails_on_a_dockerfile_buildkit_rejects(c, monkeypatch, tmp_path):
    """The half that proves the test above is not vacuous. `FromAsCasing` fires on a lowercase `as`
    beside an uppercase `FROM` — a rule hadolint does not carry, so this is also evidence the two
    tools cover different ground."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch as builder\nCOPY Dockerfile /Dockerfile\n")
    image = DockerImage(name="casing", path=tmp_path, dockerfile=dockerfile, image="casing-test", group="casing")
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [image])
    with pytest.raises(UnexpectedExit):
        docker.check.body(c)


def test_check_noops_cleanly_in_a_repo_with_no_images(c, monkeypatch, capsys):
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [])
    docker.check.body(c)
    assert "nothing to do" in capsys.readouterr().out


def test_build_and_push_round_trip(c, monkeypatch, tmp_path, docker_registry):
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\nCOPY Dockerfile /Dockerfile\n")
    image = DockerImage(
        name="scratch",
        path=tmp_path,
        dockerfile=dockerfile,
        image=f"{docker_registry}/scratch-test",
        group="scratch",
    )
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [image])
    monkeypatch.setattr(docker, "current_version", lambda c, group=None: "test")

    docker.build.body(c)
    docker.push.body(c)

    url = f"http://{docker_registry}/v2/scratch-test/tags/list"
    with cast(http.client.HTTPResponse, urllib.request.urlopen(url)) as response:
        body = response.read()
    tags = cast(dict[str, object], json.loads(body))["tags"]
    assert tags == ["test"]

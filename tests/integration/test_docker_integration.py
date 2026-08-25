"""Real, non-mocked round trip for repo_tasks.docker against a local registry:3 container (see
conftest.py's docker_registry fixture): build and push a throwaway image, then confirm the pushed
tag is actually queryable back from the registry's own API — unlike tests/test_docker.py's unit
tests, this exercises real `docker build`/`docker push` against a real (if local) registry."""

import http.client
import json
import urllib.request
from typing import cast

from repo_tasks import docker
from repo_tasks.projects import DockerImage


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

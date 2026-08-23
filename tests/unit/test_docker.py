"""Tests for repo_tasks.docker: command-string construction for build/push/release, with
discover_docker_images/current_version mocked out via monkeypatch — projects.py/version.py own
their own tests for the real discovery/version-resolution logic."""

from pathlib import Path

import pytest

from repo_tasks import docker
from repo_tasks.projects import DockerImage


def _stub_image(**overrides):
    defaults = {
        "name": "sample-service",
        "path": Path("examples/sample-service"),
        "dockerfile": Path("examples/sample-service/Dockerfile"),
        "image": "ghcr.io/org/sample-service",
        "group": "sample-service",
    }
    defaults.update(overrides)
    return DockerImage(**defaults)  # pyright: ignore[reportArgumentType]


def _stub(monkeypatch, image=None, version="1.2.3"):
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [image or _stub_image()])
    monkeypatch.setattr(docker, "current_version", lambda c, group=None: version)


def test_build_default_tag_from_current_version(c, monkeypatch):
    _stub(monkeypatch)
    docker.build.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(
        "docker build -t ghcr.io/org/sample-service:1.2.3 -f examples/sample-service/Dockerfile "
        "examples/sample-service",
        echo=True,
    )


def test_build_tag_override(c, monkeypatch):
    _stub(monkeypatch)
    docker.build.body(c, tag="dev")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(
        "docker build -t ghcr.io/org/sample-service:dev -f examples/sample-service/Dockerfile examples/sample-service",
        echo=True,
    )


def test_build_with_platforms_uses_buildx_and_pushes(c, monkeypatch):
    _stub(monkeypatch)
    docker.build.body(c, platforms="linux/amd64,linux/arm64")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with(
        "docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/org/sample-service:1.2.3 "
        "-f examples/sample-service/Dockerfile examples/sample-service --push",
        echo=True,
    )


def test_push_default_tag_from_current_version(c, monkeypatch):
    _stub(monkeypatch)
    docker.push.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("docker push ghcr.io/org/sample-service:1.2.3", echo=True)


def test_push_tag_override(c, monkeypatch):
    _stub(monkeypatch)
    docker.push.body(c, tag="dev")  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("docker push ghcr.io/org/sample-service:dev", echo=True)


def test_release_builds_tags_and_pushes_version_and_latest(c, monkeypatch):
    _stub(monkeypatch)
    docker.release.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [
        (
            (
                "docker build -t ghcr.io/org/sample-service:1.2.3 -f examples/sample-service/Dockerfile "
                "examples/sample-service",
            ),
            {"echo": True},
        ),
        (("docker tag ghcr.io/org/sample-service:1.2.3 ghcr.io/org/sample-service:latest",), {"echo": True}),
        (("docker push ghcr.io/org/sample-service:1.2.3",), {"echo": True}),
        (("docker push ghcr.io/org/sample-service:latest",), {"echo": True}),
    ]


def test_resolve_image_raises_when_project_not_found(c, monkeypatch):
    _stub(monkeypatch)
    with pytest.raises(ValueError, match="nonexistent"):
        docker.build.body(c, project="nonexistent")  # pyright: ignore[reportAny, reportFunctionMemberAccess]


def test_resolve_image_raises_when_none_discovered(c, monkeypatch):
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [])
    with pytest.raises(ValueError, match="no docker image found"):
        docker.build.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]

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
    docker.build.body(c)
    c.run.assert_called_once_with(
        "docker build -t ghcr.io/org/sample-service:1.2.3 -f examples/sample-service/Dockerfile "
        "examples/sample-service",
        echo=True,
    )


def test_build_tag_override(c, monkeypatch):
    _stub(monkeypatch)
    docker.build.body(c, tag="dev")
    c.run.assert_called_once_with(
        "docker build -t ghcr.io/org/sample-service:dev -f examples/sample-service/Dockerfile examples/sample-service",
        echo=True,
    )


def test_build_with_platforms_uses_buildx_and_pushes(c, monkeypatch):
    _stub(monkeypatch)
    docker.build.body(c, platforms="linux/amd64,linux/arm64")
    c.run.assert_called_once_with(
        "docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/org/sample-service:1.2.3 "
        "-f examples/sample-service/Dockerfile examples/sample-service --push",
        echo=True,
    )


def test_push_default_tag_from_current_version(c, monkeypatch):
    _stub(monkeypatch)
    docker.push.body(c)
    c.run.assert_called_once_with("docker push ghcr.io/org/sample-service:1.2.3", echo=True)


def test_push_tag_override(c, monkeypatch):
    _stub(monkeypatch)
    docker.push.body(c, tag="dev")
    c.run.assert_called_once_with("docker push ghcr.io/org/sample-service:dev", echo=True)


def test_release_builds_tags_and_pushes_version_and_latest(c, monkeypatch):
    _stub(monkeypatch)
    docker.release.body(c)
    assert c.run.call_args_list == [
        (
            (
                "docker build -t ghcr.io/org/sample-service:1.2.3 -f examples/sample-service/Dockerfile "
                "examples/sample-service",
            ),
            {"echo": True},
        ),
        (("docker push ghcr.io/org/sample-service:1.2.3",), {"echo": True}),
        (("docker tag ghcr.io/org/sample-service:1.2.3 ghcr.io/org/sample-service:latest",), {"echo": True}),
        (("docker push ghcr.io/org/sample-service:latest",), {"echo": True}),
    ]


@pytest.mark.parametrize("pep440", ["1.2.3rc1", "1.2.4.dev5+gabc1234"])
def test_release_never_tags_a_prerelease_latest(c, monkeypatch, capsys, pep440):
    """`latest` is the one tag that opts every puller in; an rc or dev build stays opt-in."""
    _stub(monkeypatch, version=pep440)
    docker.release.body(c)
    call_strings = [call[0][0] for call in c.run.call_args_list]
    assert not any("latest" in s for s in call_strings)
    assert "not tagged latest" in capsys.readouterr().out


def test_build_tags_the_semver_spelling_of_a_release_candidate(c, monkeypatch):
    _stub(monkeypatch, version="1.2.3rc2")
    docker.build.body(c)
    c.run.assert_called_once_with(
        "docker build -t ghcr.io/org/sample-service:1.2.3-rc.2 -f examples/sample-service/Dockerfile "
        "examples/sample-service",
        echo=True,
    )


def test_build_dev_rewrites_the_version_before_building(c, monkeypatch):
    _stub(monkeypatch, version="1.2.4.dev5+gabc1234")
    seen = []
    monkeypatch.setattr(docker, "set_dev", lambda c, group=None: seen.append(group))
    docker.build.body(c, dev=True)
    assert seen == ["sample-service"]
    c.run.assert_called_once_with(
        "docker build -t ghcr.io/org/sample-service:1.2.4-dev.5.gabc1234 -f examples/sample-service/Dockerfile "
        "examples/sample-service",
        echo=True,
    )


def test_resolve_image_raises_when_project_not_found(c, monkeypatch):
    _stub(monkeypatch)
    with pytest.raises(ValueError, match="nonexistent"):
        docker.build.body(c, project="nonexistent")


def test_check_runs_build_check_for_each_discovered_image(c, monkeypatch):
    # Every image, unlike build/push/release: a check that reported only the first repo's findings
    # would be one that quietly ignores the rest of the repo.
    second = _stub_image(name="api", path=Path("services/api"), dockerfile=Path("services/api/Dockerfile"))
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [_stub_image(), second])
    docker.check.body(c)
    assert c.run.call_args_list == [
        (("docker build --check -f examples/sample-service/Dockerfile examples/sample-service",), {"echo": True}),
        (("docker build --check -f services/api/Dockerfile services/api",), {"echo": True}),
    ]


def test_check_narrows_to_one_project(c, monkeypatch):
    second = _stub_image(name="api", path=Path("services/api"), dockerfile=Path("services/api/Dockerfile"))
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [_stub_image(), second])
    docker.check.body(c, project="api")
    c.run.assert_called_once_with("docker build --check -f services/api/Dockerfile services/api", echo=True)


@pytest.mark.parametrize("task_name", ["check", "build", "push", "release", "login"])
def test_tasks_no_op_cleanly_with_zero_images(c, monkeypatch, capsys, task_name):
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [])
    getattr(docker, task_name).body(c)  # pyright: ignore[reportAny]
    c.run.assert_not_called()
    assert "nothing to do" in capsys.readouterr().out


def test_explicit_project_still_errors_with_zero_images(c, monkeypatch):
    # Absence no-ops; a --project naming nothing is ambiguity, and stays an error.
    monkeypatch.setattr(docker, "discover_docker_images", lambda c: [])
    with pytest.raises(ValueError, match="nonexistent"):
        docker.build.body(c, project="nonexistent")


def test_login_targets_the_registry_the_image_pushes_to(c, monkeypatch):
    _stub(monkeypatch)
    docker.login.body(c)
    # pty because docker refuses to prompt for a password from a non-TTY device.
    c.run.assert_called_once_with("docker login ghcr.io", echo=True, pty=True)


def test_login_never_puts_a_credential_in_the_command(c, monkeypatch):
    # The whole point of letting docker prompt: c.run echoes its command, so anything
    # interpolated here would be printed to the terminal and into any CI log.
    _stub(monkeypatch)
    docker.login.body(c)
    assert c.run.call_args.args == ("docker login ghcr.io",)


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("ghcr.io/org/sample-service", "ghcr.io"),
        ("localhost:5000/sample-service", "localhost:5000"),
        ("localhost/sample-service", "localhost"),
        ("registry.example.com:5000/org/thing", "registry.example.com:5000"),
        # No dot, no port, not localhost: a Docker Hub namespace, not a registry.
        ("org/sample-service", "docker.io"),
        ("sample-service", "docker.io"),
    ],
)
def test_registry_host_follows_dockers_own_rule(image, expected):
    assert docker._registry_host(image) == expected

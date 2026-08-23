"""Fixtures for the opt-in integration tier (see plans/2026-08-22-local-index-and-registry-testing.md
and, for clean_os_container, plans/2026-08-23-clean-os-integration-testing.md). All fixtures are
module-scoped — the "expensive setup" this repo's python-conventions skill describes.
devpi_index/docker_registry need no per-test isolation since every test uploads/pushes its own
distinctly-named artifact; clean_os_container is currently exercised by one smoke-test module only
(see that module's docstring for the isolation caveat once a real mutating test is added).

devpi_index skips (pytest.skip) when the `devpi-server` binary isn't on PATH, since it's an
opt-in dependency group (`uv sync --group integration`) a contributor may not have installed.
docker_registry and clean_os_container have no such guard: a Docker daemon is assumed present, and
testcontainers' own connection error is left to fail the fixture (and therefore the tests) loudly
rather than skip — deliberate, see plans/2026-08-22-local-index-and-registry-testing.md.
"""

import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from invoke import Config, Context
from testcontainers.core.container import DockerContainer

_REPO_ROOT = Path(__file__).parent.parent.parent
_CLEAN_OS_IMAGE_TAG = "repo-tasks-clean-os-test:latest"


@pytest.fixture
def c():
    """A real (non-Mock) invoke Context, wired for these tasks' actual c.run() calls to execute —
    in_stream disabled since invoke's default stdin-forwarding thread otherwise collides with
    pytest's own captured stdin (OSError: reading from stdin while output is captured)."""
    return Context(config=Config(overrides={"run": {"in_stream": False}}))


@dataclass(frozen=True)
class DevpiIndex:
    upload_url: str
    simple_url: str
    username: str
    password: str


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return cast(int, s.getsockname()[1])


def _run_devpi_client(clientdir: Path, *args: str) -> None:
    subprocess.run(["devpi", *args, "--clientdir", str(clientdir)], check=True, capture_output=True, text=True)


def _wait_until_up(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
        else:
            return
    raise TimeoutError(f"devpi-server never came up at {url}")


@pytest.fixture(scope="module")
def devpi_index(tmp_path_factory):
    if shutil.which("devpi-server") is None:
        pytest.skip("devpi-server not installed — run `uv sync --group integration` to enable this tier")

    serverdir = tmp_path_factory.mktemp("devpi-server")
    password = "test"
    subprocess.run(
        ["devpi-init", "--serverdir", str(serverdir), "--root-passwd", password], check=True, capture_output=True
    )

    port = _free_port()
    process = subprocess.Popen(
        ["devpi-server", "--serverdir", str(serverdir), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        # The server root, not /root/pypi/ — the latter is the live PyPI mirror index, whose
        # first hit can trigger a slow (or, in a sandboxed environment, blocked) upstream fetch.
        _wait_until_up(f"http://127.0.0.1:{port}/")

        clientdir = tmp_path_factory.mktemp("devpi-client")
        _run_devpi_client(clientdir, "use", f"http://127.0.0.1:{port}")
        _run_devpi_client(clientdir, "login", "root", "--password", password)
        _run_devpi_client(clientdir, "index", "-c", "test", "bases=root/pypi")

        yield DevpiIndex(
            upload_url=f"http://127.0.0.1:{port}/root/test/",
            simple_url=f"http://127.0.0.1:{port}/root/test/+simple",
            username="root",
            password=password,
        )
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="module")
def docker_registry():
    with DockerContainer("registry:3").with_exposed_ports(5000) as registry:
        # 127.0.0.1 explicitly, not localhost — Docker's insecure-registry auto-exemption
        # reliably covers the literal loopback address but isn't guaranteed for the hostname.
        yield f"127.0.0.1:{registry.get_exposed_port(5000)}"


@pytest.fixture(scope="module")
def clean_os_container():
    """A running, non-root container with a fresh $HOME and a writable copy of this repo's source
    at /home/tester/repo-tasks — for testing repo-tasks' own user-wide effects (selfinstall.py,
    agents.py, direnv.py, configs.py) without touching the real dev machine's $HOME. See
    plans/2026-08-23-clean-os-integration-testing.md.

    Built via a plain `docker build` subprocess, not testcontainers' DockerImage (which shells out
    to docker-py's images.build()) — docker-py's build() eagerly resolves credentials for every
    registry listed in ~/.docker/config.json before building anything, so a stale/broken credential
    helper for a registry this build never even touches (e.g. a dead `docker-credential-gcloud`)
    fails the whole build. Plain `docker build` doesn't do that eager resolution. Matches this
    repo's own docker.py build task, which shells out the same way rather than using the SDK.
    """
    integration_dir = Path(__file__).parent
    subprocess.run(
        ["docker", "build", "-f", "clean-os.Dockerfile", "-t", _CLEAN_OS_IMAGE_TAG, "."],
        cwd=integration_dir,
        check=True,
    )
    container = DockerContainer(_CLEAN_OS_IMAGE_TAG).with_command("sleep infinity")
    container.with_volume_mapping(str(_REPO_ROOT), "/repo-src", mode="ro")
    with container:
        copy = container.exec(["cp", "-r", "/repo-src", "/home/tester/repo-tasks"])
        assert copy.exit_code == 0, copy.output.decode()
        yield container

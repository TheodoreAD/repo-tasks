"""Fixtures for the opt-in integration tier (see plans/2026-08-22-local-index-and-registry-testing.md).
Both fixtures are module-scoped — the "expensive setup" this repo's python-conventions skill
describes — since nothing here needs per-test isolation: every test uploads/pushes its own
distinctly-named artifact.

devpi_index skips (pytest.skip) when the `devpi-server` binary isn't on PATH, since it's an
opt-in dependency group (`uv sync --group integration`) a contributor may not have installed.
docker_registry has no such guard: a Docker daemon is assumed present, and testcontainers' own
connection error is left to fail the fixture (and therefore the tests) loudly rather than skip —
deliberate, see plans/2026-08-22-local-index-and-registry-testing.md.
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

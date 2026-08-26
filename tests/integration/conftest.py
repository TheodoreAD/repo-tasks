"""Fixtures for the opt-in integration tier (see contributing/test-tiers.md). All fixtures are
module-scoped — the "expensive setup" this repo's python-conventions skill describes.
devpi_index/docker_registry need no per-test isolation since every test uploads/pushes its own
distinctly-named artifact; clean_os_container relies on module scope meaning one container *per
module* — the smoke-test module and the mutating test_clean_os_user_effects.py module each get
their own fresh container, and the isolation rules within the mutating module live in that
module's own docstring.

devpi_index still skips (pytest.skip) when the `devpi-server` binary isn't on PATH. That is now a
belt-and-braces guard rather than the main path — devpi lives in `dev` like everything else, so a
plain `inv venv.sync` installs it — but it keeps the tier honest on a half-synced environment.
docker_registry and clean_os_container have no such guard: a Docker daemon is assumed present, and
testcontainers' own connection error is left to fail the fixture (and therefore the tests) loudly
rather than skip — deliberate, see contributing/test-tiers.md.
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

from repo_tasks import docker as docker_tasks
from repo_tasks.projects import DockerImage

_REPO_ROOT = Path(__file__).parent.parent.parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tolerate ResourceWarning in this tier only — pytest.ini makes every warning an error.

    This tier launches subprocesses and containers, and testcontainers/docker-py leave socket and
    pipe objects for the garbage collector. The GC finalizes them at an arbitrary later moment, so
    the unraisable plugin reports the warning against whichever test happens to be running:
    measured, `test_stamp_script_is_shfmt_clean` failed in a full-tier run and passed in isolation.
    A failure that moves between innocent tests is worse than the leak it describes.

    Deliberately not in pytest.ini, which ships to every consumer: the unit tier never shells out,
    so a ResourceWarning there is always this repo's own leak and stays fatal. That is not
    theoretical — it caught one the day this landed, in the devpi fixture below.
    """
    for item in items:
        item.add_marker(pytest.mark.filterwarnings("ignore::ResourceWarning"))


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
        pytest.skip("devpi-server not installed — run `inv venv.sync` to restore the dev environment")

    serverdir = tmp_path_factory.mktemp("devpi-server")
    password = "test"
    subprocess.run(
        ["devpi-init", "--serverdir", str(serverdir), "--root-passwd", password], check=True, capture_output=True
    )

    port = _free_port()
    # `with`, not a bare Popen: terminate()/wait() end the process but never close the stdout pipe,
    # leaving the BufferedReader for the garbage collector to finalize — which raises ResourceWarning
    # at an arbitrary later moment, so pytest's unraisable plugin blames whichever test happens to be
    # running rather than this fixture. Popen.__exit__ closes the pipes.
    with subprocess.Popen(
        ["devpi-server", "--serverdir", str(serverdir), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
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
def clean_os_container(docker_registry):
    """A running, non-root container with a fresh $HOME and a writable copy of this repo's source
    at /home/tester/repo-tasks — for testing repo-tasks' own user-wide effects (selfinstall.py,
    agents.py, direnv.py, configs.py) without touching the real dev machine's $HOME. See
    contributing/test-tiers.md's clean-OS section.

    Built and published via repo_tasks.docker's own real build/push/release tasks (dogfooding —
    the whole point of this fixture, per that plan) — same monkeypatched-discover_docker_images
    pattern test_docker_integration.py already uses, pointed at clean-os.Dockerfile instead of a
    synthetic `FROM scratch` image, and pushed to this module's real (if local) docker_registry
    instead of the test's own throwaway image. NOT testcontainers' DockerImage, which shells out to
    docker-py's images.build() — docker-py eagerly resolves credentials for every registry listed
    in ~/.docker/config.json before building anything, so a stale/broken credential helper for a
    registry the build never even touches (e.g. a dead `docker-credential-gcloud`) fails the whole
    build. docker.py's own build/push tasks just shell out to the plain `docker` CLI, which doesn't
    do that eager resolution.

    Uses a fresh Context, not the `c` fixture — `c` is function-scoped and a module-scoped fixture
    can't depend on it (pytest scope mismatch); `pytest.MonkeyPatch()` similarly stands in for the
    function-scoped `monkeypatch` fixture for the same reason.
    """
    integration_dir = Path(__file__).parent
    image = DockerImage(
        name="clean-os-test",
        path=integration_dir,
        dockerfile=integration_dir / "clean-os.Dockerfile",
        image=f"{docker_registry}/clean-os-test",
        group="clean-os-test",
    )
    ctx = Context(config=Config(overrides={"run": {"in_stream": False}}))
    mp = pytest.MonkeyPatch()
    mp.setattr(docker_tasks, "discover_docker_images", lambda c: [image])
    mp.setattr(docker_tasks, "current_version", lambda c, group=None: "test")
    try:
        # build -> tag :latest -> push :test -> push :latest
        docker_tasks.release.body(ctx)
    finally:
        mp.undo()

    container = DockerContainer(f"{image.image}:latest").with_command("sleep infinity")
    container.with_volume_mapping(str(_REPO_ROOT), "/repo-src", mode="ro")
    with container:
        # tar with excludes, not plain `cp -r` — the host checkout drags a multi-hundred-MB .venv
        # (useless inside the container: host paths, host interpreter) plus tool caches into every
        # container otherwise.
        copy = container.exec(
            [
                "bash",
                "-c",
                "mkdir /home/tester/repo-tasks && tar -C /repo-src"
                " --exclude=.venv --exclude=.pytest_cache --exclude=.ruff_cache --exclude=__pycache__"
                " -cf - . | tar -C /home/tester/repo-tasks -xf -",
            ]
        )
        assert copy.exit_code == 0, copy.output.decode()
        yield container

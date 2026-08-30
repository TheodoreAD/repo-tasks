"""Fixtures for the opt-in integration tier (see contributing/test-tiers.md). All fixtures are
module-scoped — the "expensive setup" this repo's python-conventions skill describes.
package_index/docker_registry need no per-test isolation since every test uploads/pushes its own
distinctly-named artifact; clean_os_container relies on module scope meaning one container *per
module* — the smoke-test module and the mutating test_clean_os_user_effects.py module each get
their own fresh container, and the isolation rules within the mutating module live in that
module's own docstring.

package_index still skips (pytest.skip) when the `pypi-server` binary isn't on PATH. That is a
belt-and-braces guard rather than the main path — pypiserver lives in `dev` like everything else, so
a plain `inv venv.sync` installs it — but it keeps the tier honest on a half-synced environment.
docker_registry and clean_os_container have no such guard: a Docker daemon is assumed present, and
testcontainers' own connection error is left to fail the fixture (and therefore the tests) loudly
rather than skip — deliberate, see contributing/test-tiers.md.
"""

import http.server
import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import cast, final

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
    theoretical — it caught one the day this landed, in the index fixture below.
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
class PackageIndex:
    upload_url: str
    simple_url: str
    username: str
    password: str


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return cast(int, s.getsockname()[1])


def _wait_until_up(url: str, what: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
        else:
            return
    raise TimeoutError(f"{what} never came up at {url}")


@pytest.fixture(scope="module")
def package_index(tmp_path_factory):
    """A real PEP 503 index that accepts a real `uv publish` upload.

    pypiserver rather than devpi: it serves the HTML branch `dist.list_versions` falls back to —
    `#sha256=` fragments included, which is one of the two bugs this tier originally caught — for 4
    resolved packages instead of 61, and without devpi's `setuptools<=81` pin. It serves no PEP 691
    JSON at all (measured 2026-08-30: it returns `text/html` whatever the Accept header says), so
    the JSON branch gets `json_index` below instead. See contributing/test-tiers.md.
    """
    if shutil.which("pypi-server") is None:
        pytest.skip("pypiserver not installed — run `inv venv.sync` to restore the dev environment")

    packages = tmp_path_factory.mktemp("pypiserver-packages")
    port = _free_port()
    # `with`, not a bare Popen: terminate()/wait() end the process but never close the stdout pipe,
    # leaving the BufferedReader for the garbage collector to finalize — which raises ResourceWarning
    # at an arbitrary later moment, so pytest's unraisable plugin blames whichever test happens to be
    # running rather than this fixture. Popen.__exit__ closes the pipes.
    with subprocess.Popen(
        # `-P . -a .` disables authentication entirely: this index exists for the length of one test
        # module and holds only artifacts the tests just built, so a credential would be ceremony.
        # `uv publish` still needs *some* -u/-p pair, which the empty strings below supply.
        #
        # `--overwrite` because the index is module-scoped while every test publishes the repo's own
        # wheel — the same filename each time. Without it the second upload is a 409, and devpi
        # (which this replaced) simply tolerated the re-upload. Each test doing its own full
        # build-publish-read round trip is the point of the tier, so the fixture yields rather than
        # the upload being hoisted into it.
        ["pypi-server", "run", "-p", str(port), "-P", ".", "-a", ".", "--overwrite", str(packages)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as process:
        try:
            _wait_until_up(f"http://127.0.0.1:{port}/", "pypiserver")
            yield PackageIndex(
                upload_url=f"http://127.0.0.1:{port}/",
                simple_url=f"http://127.0.0.1:{port}/simple",
                username="",
                password="",
            )
        finally:
            process.terminate()
            process.wait(timeout=10)


@final
class JsonIndex:
    """A stub PEP 691 index: serves one canned body and records the Accept header it was asked with.

    Everything a test needs hangs off this object rather than off module-level helpers, because
    `tests/` is deliberately not a package (see contributing/type-checking.md) — so a test module
    cannot import from its own conftest by name, and `import conftest` would be ambiguous between
    this file and `tests/conftest.py`.
    """

    def __init__(self) -> None:
        self._payload = b"{}"
        self.seen_accept: list[str] = []
        index = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                index.seen_accept.append(self.headers.get("Accept", ""))
                body = index._payload
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.pypi.simple.v1+json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                _ = self.wfile.write(body)

            # A002: the parameter shadows a builtin, but it is BaseHTTPRequestHandler's own name and
            # renaming it is a reportIncompatibleMethodOverride error. reportImplicitOverride:
            # typing.override is 3.12+ and this repo's floor is 3.11.
            def log_message(self, format: str, *args: object) -> None:  # noqa: A002 # pyright: ignore[reportImplicitOverride]
                """Silence the per-request stderr line; a failing test says more than an access log."""

        self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def serve(self, payload: object) -> str:
        """Point the stub at one PEP 691 body; returns the simple-index URL to query it through."""
        self._payload = json.dumps(payload).encode()
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host!s}:{port}/simple"


@pytest.fixture
def json_index():
    """The JSON branch, which no lightweight real index serves.

    Deliberately a stub, and it covers *more* than a real server could: `_json_versions` has three
    sub-paths — a top-level `versions` key, a per-file `version` key, and deriving the version from
    the filename — and nothing real emits all three. Measured 2026-08-30: PyPI takes the first (and
    omits the per-file key entirely), devpi took the third, and nothing produces the second, which
    was mock-only until this fixture existed.

    What it adds over tests/unit/test_dist.py's mocked equivalents is the wire: each request is a
    real socket round trip, so `seen_accept` proves `dist.list_versions` actually sent the JSON
    media type rather than merely being written as though it does. A mocked `_get` cannot show that.
    """
    index = JsonIndex()
    index._thread.start()
    try:
        yield index
    finally:
        index._server.shutdown()
        index._server.server_close()
        index._thread.join(timeout=5)


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
    # A final version, not a dev build: `release` skips the `latest` tag for a pre-release, and
    # `latest` is the tag the container below is started from.
    mp.setattr(docker_tasks, "current_version", lambda c, group=None: "0.0.0")
    try:
        # build -> tag :latest -> push :0.0.0 -> push :latest
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

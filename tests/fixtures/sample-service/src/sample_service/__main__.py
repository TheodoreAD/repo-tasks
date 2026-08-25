"""The service itself: one stdlib `http.server` answering `/healthz` and `/`, no dependencies.

Small on purpose. What it serves matters far less than what it proves — that the image the
Dockerfile builds really does run the wheel `inv dist.build` produced, at the version
`inv version.bump` wrote, deployed by the chart that shares its version group.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import PackageNotFoundError, version

_DEFAULT_PORT = 8000


def _service_version() -> str:
    """The installed distribution's own version — never a constant in this source tree. Falls
    back only when running from a source checkout that was never installed (no dist metadata)."""
    try:
        return version("sample-service")
    except PackageNotFoundError:
        return "unknown"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # BaseHTTPRequestHandler dispatches on this exact name
        if self.path not in ("/", "/healthz"):
            self.send_error(404)
            return
        body = json.dumps({"service": "sample-service", "version": _service_version(), "status": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        _ = self.wfile.write(body)

    # No `@override`: `typing.override` is 3.12+, this fixture declares >=3.11 and has no dependencies
    # to pull `typing_extensions` from. Suppressed per line so the shared config's
    # `failOnWarnings` can stay on.
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 — the stdlib's own name  # pyright: ignore[reportImplicitOverride]
        """Log to stdout rather than stderr, so a container's logs aren't all error-stream."""
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    port = int(os.environ.get("PORT", _DEFAULT_PORT))
    server = ThreadingHTTPServer(("", port), Handler)
    print(f"sample-service {_service_version()} listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

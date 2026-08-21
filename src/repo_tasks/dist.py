"""Python distribution build/publish/query tasks (build a wheel, publish it, list a project's
published versions). Never touches .venv or installs anything editable — `uv build` always
produces a real, non-editable sdist/wheel regardless of how the *dev* environment happens to be
installed, so this module has no interaction with venv.py's --no-editable/CI-mode design."""

import http.client
import json
import re
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

from invoke import task

from .projects import discover_python_projects

_DIST_DIR = Path("dist")
_DEFAULT_INDEX = "https://pypi.org/simple"
_JSON_ACCEPT = "application/vnd.pypi.simple.v1+json"


class _NotFoundError(Exception):
    """The project has no releases at the queried index (a 404 response)."""


def _normalize(name: str) -> str:
    """PEP 503 project-name normalization."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _version_sort_key(version: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", version)]


def _version_from_filename(filename: str, normalized_name: str) -> str | None:
    if filename.endswith(".whl"):
        # {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
        parts = filename[: -len(".whl")].split("-")
        return parts[1] if len(parts) >= 5 else None
    for ext in (".tar.gz", ".zip"):
        if not filename.endswith(ext):
            continue
        stem = filename[: -len(ext)]
        prefix = f"{normalized_name}-"
        if _normalize(stem).startswith(prefix):
            return stem[len(prefix) :]
    return None


def _get(url: str, accept: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": accept} if accept else {})
    try:
        with cast(http.client.HTTPResponse, urllib.request.urlopen(request)) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise _NotFoundError from e
        raise


def _json_versions(payload: bytes) -> list[str]:
    data = cast(dict[str, object], json.loads(payload))
    found = data.get("versions")
    if found:
        return [str(v) for v in cast(list[object], found)]
    files = cast(list[dict[str, object]], data.get("files", []))
    return sorted({str(f["version"]) for f in files if "version" in f})


def _html_versions(payload: bytes, normalized_name: str) -> list[str]:
    filenames = cast(list[str], re.findall(r'href="[^"]*/([^"/]+)"', payload.decode()))
    return sorted({v for fn in filenames if (v := _version_from_filename(fn, normalized_name)) is not None})


@task
def clean(c):
    """Remove the built dist/ directory."""
    if not _DIST_DIR.exists():
        print("[dist.clean] dist/ not present — nothing to clean")
        return
    shutil.rmtree(_DIST_DIR)
    print("[dist.clean] dist/ removed")


@task(
    pre=[clean],
    help={
        "project": "Project to build (Phase 1: ignored, single implicit project)",
        "sdist": "Build sdist+wheel instead of wheel-only",
    },
)
def build(c, project=None, sdist=False):
    """Build a wheel (default) or sdist+wheel pair (uv build), always into a freshly-cleaned
    dist/ — a stale wheel from a previous version can never survive into a fresh build."""
    c.run("uv build" if sdist else "uv build --wheel", echo=True)


@task(
    pre=[build],
    help={
        "project": "Project to publish (Phase 1: ignored, single implicit project)",
        "index": "Package index to publish to (default: uv's own config/PyPI default)",
        "dry_run": "Pass --dry-run through to uv publish — safe to run against a real index",
    },
)
def publish(c, project=None, index=None, dry_run=False):
    """Publish dist/* to a package index (uv publish). Always builds fresh first (pre=[build],
    which itself implies clean) — publish never ships stale state."""
    cmd = "uv publish"
    if index:
        cmd += f" --index {index}"
    if dry_run:
        cmd += " --dry-run"
    c.run(cmd, echo=True)


@task(
    help={
        "project": "Project to query (Phase 1: ignored, single implicit project)",
        "index": "Package index base URL to query (default: PyPI)",
    }
)
def versions(c, project=None, index=None):
    """List a project's published versions from a package index — PEP 691 JSON Simple API,
    falling back to the PEP 503 HTML file listing if the index doesn't serve the JSON media
    type. Works unmodified against PyPI, TestPyPI, or any private PEP 503/691-compliant index."""
    name = discover_python_projects(c)[0].name  # Phase 1: single implicit project
    normalized = _normalize(name)
    base = (index or _DEFAULT_INDEX).rstrip("/")
    url = f"{base}/{normalized}/"

    try:
        try:
            found = _json_versions(_get(url, accept=_JSON_ACCEPT))
        except (json.JSONDecodeError, urllib.error.URLError):
            found = _html_versions(_get(url), normalized)
    except _NotFoundError:
        found = []

    if not found:
        print(f"[dist.versions] no releases found for {name!r} at {base}")
        return
    for v in sorted(found, key=_version_sort_key):
        print(v)

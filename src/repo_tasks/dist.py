"""Python distribution build/publish/query tasks (build a wheel, publish it, list a project's
published versions). Never touches .venv or installs anything editable — `uv build` always
produces a real, non-editable sdist/wheel regardless of how the *dev* environment happens to be
installed, so this module has no interaction with venv.py's --no-editable/CI-mode design."""

import http.client
import json
import re
import shlex
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Exit, task

from .nextsteps import next_steps
from .projects import PythonProject, discover_python_projects
from .requirements import NETWORK, requires
from .version import Version, set_dev

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


def _json_versions(payload: bytes, normalized_name: str) -> list[str]:
    data = cast(dict[str, object], json.loads(payload))
    found = data.get("versions")
    if found:
        return [str(v) for v in cast(list[object], found)]
    files = cast(list[dict[str, object]], data.get("files", []))
    versions: set[str] = set()
    for f in files:
        if "version" in f:
            versions.add(str(f["version"]))
            continue
        # PEP 691's per-file "version" key is optional and widely omitted — PyPI itself does not
        # emit it (measured 2026-08-30), and neither did devpi. PyPI is only saved from this branch
        # by supplying the top-level "versions" key above; an index that omits both lands here, so
        # fall back to deriving the version from the filename as the HTML path already does.
        filename = f.get("filename")
        if isinstance(filename, str) and (v := _version_from_filename(filename, normalized_name)) is not None:
            versions.add(v)
    return sorted(versions)


def _html_versions(payload: bytes, normalized_name: str) -> list[str]:
    # Real PEP 503 indices (PyPI itself, pypiserver, devpi) commonly append a #sha256=... fragment to the
    # href — stop the capture at '#' too, or the fragment rides along and _version_from_filename
    # never matches the (now-mangled) "filename".
    filenames = cast(list[str], re.findall(r'href="[^"]*/([^"/#]+)', payload.decode()))
    return sorted({v for fn in filenames if (v := _version_from_filename(fn, normalized_name)) is not None})


_NO_PROJECTS = "no python project (no pyproject.toml [project] table and no workspace members) — nothing to do"


def _resolve_project(c: Context, project: str | None) -> PythonProject | None:
    """The python project to act on: the named one, or the repo's own (root-first ordering in
    projects.py) when no --project narrows it down — or None when the repo has no python project
    at all, which tasks no-op cleanly on. An explicit --project naming nothing is an error, never
    a silent fallback to the root."""
    python_projects = discover_python_projects(c)
    if project is None:
        return python_projects[0] if python_projects else None
    matches = [p for p in python_projects if p.name == project]
    if not matches:
        raise ValueError(f"no python project found for {project!r}")
    return matches[0]


@task
def clean(c: Context):
    """Remove the built dist/ directory."""
    if not _DIST_DIR.exists():
        print("[dist.clean] dist/ not present — nothing to clean")
        return
    shutil.rmtree(_DIST_DIR)
    print("[dist.clean] dist/ removed")


@task(
    pre=[clean],
    help={
        "project": "Project to build (default: the repo's own root project)",
        "sdist": "Build sdist+wheel instead of wheel-only",
        "dev": "Build a dev-build version (X.Y.Z.devN+gHASH) — rewrites the working tree's version first, uncommitted",
    },
)
def build(c: Context, project: str | None = None, sdist: bool = False, dev: bool = False):
    """Build a wheel (default) or sdist+wheel pair (uv build), always into a freshly-cleaned
    dist/ — a stale wheel from a previous version can never survive into a fresh build.

    Always names the target with `--package`, workspace or not: a single-project repo is its own
    workspace of one to uv, so the flag is a no-op there and the command stays identical across
    both shapes. No-ops cleanly in a repo with no python project."""
    target = _resolve_project(c, project)
    if target is None:
        print(f"[dist.build] {_NO_PROJECTS}")
        return
    if dev:
        set_dev(c, group=target.name)
    cmd = "uv build" if sdist else "uv build --wheel"
    c.run(f"{cmd} --package {target.name}", echo=True)


@requires(NETWORK)
@task(
    help={
        "project": "Project to publish (default: the repo's own root project)",
        "index": "Package index to publish to (default: uv's own config/PyPI default)",
        "dry_run": "Pass --dry-run through to uv publish — safe to run against a real index",
    },
)
def publish(c: Context, project: str | None = None, index: str | None = None, dry_run: bool = False):
    """Publish dist/* to a package index (uv publish). Always cleans and builds fresh first —
    publish never ships stale state.

    Those two run from this body rather than as `pre=[build]`: invoke's pre-tasks take no
    arguments from the caller, so a pre-built `build` would always build the *root* project and
    silently publish the wrong wheel for `--project=<member>`. No-ops cleanly, as one unit, in a
    repo with no python project."""
    target = _resolve_project(c, project)
    if target is None:
        print(f"[dist.publish] {_NO_PROJECTS}")
        return
    # A dev build carries a local version (+gHASH), which PyPI rejects outright; only a named
    # index — the private/test one a dev build is for — may receive it. Said here, before uv
    # builds and then fails at upload time.
    if Version.parse(target.version).dev is not None and index is None:
        raise ValueError(f"{target.version} is a dev build — publish it with --index <private index>, never to PyPI")
    clean(c)
    build(c, project=project)
    cmd = "uv publish"
    if index:
        cmd += f" --index {index}"
    if dry_run:
        cmd += " --dry-run"
    c.run(cmd, echo=True)


@requires(NETWORK)
@task(
    help={
        "project": "Project to query (default: the repo's own root project)",
        "index": "Package index base URL to query (default: PyPI)",
    }
)
def list_versions(c: Context, project: str | None = None, index: str | None = None):
    """List a project's published versions from a package index — PEP 691 JSON Simple API,
    falling back to the PEP 503 HTML file listing if the index doesn't serve the JSON media
    type. Works unmodified against PyPI, TestPyPI, or any private PEP 503/691-compliant index.
    No-ops cleanly in a repo with no python project."""
    target = _resolve_project(c, project)
    if target is None:
        print(f"[dist.list_versions] {_NO_PROJECTS}")
        return
    name = target.name
    normalized = _normalize(name)
    base = (index or _DEFAULT_INDEX).rstrip("/")
    url = f"{base}/{normalized}/"

    try:
        try:
            found = _json_versions(_get(url, accept=_JSON_ACCEPT), normalized)
        except (json.JSONDecodeError, urllib.error.URLError):
            found = _html_versions(_get(url), normalized)
    except _NotFoundError:
        found = []

    if not found:
        print(f"[dist.list_versions] no releases found for {name!r} at {base}")
        return
    for v in sorted(found, key=_version_sort_key):
        print(v)


_LOCK_PATH = Path("uv.lock")

# Run by the clean venv's own interpreter: import every top-level package or module the named
# distribution installed, read from its own file list since a distribution name is not an import
# name. Exit 3 means there is no such distribution — a virtual workspace root, which installs nothing.
_IMPORT_DISTRIBUTION = """\
import importlib.metadata, sys
try:
    files = importlib.metadata.distribution(sys.argv[1]).files or []
except importlib.metadata.PackageNotFoundError:
    sys.exit(3)
tops = sorted({
    f.parts[0].removesuffix(".py") for f in files
    if f.parts[0] != ".." and not f.parts[0].endswith((".dist-info", ".data"))
    and (len(f.parts) > 1 or f.suffix == ".py")
})
for top in tops:
    __import__(top)
print(" ".join(tops))
"""

_NOT_A_PACKAGE = 3


def _isolated_import(c: Context, project: PythonProject, workdir: str) -> tuple[bool, str]:
    """Install `project`'s declared closure alone into a fresh venv and import it. Returns whether
    it imported, and the line to report."""
    reqs, venv = f"{workdir}/{project.name}.txt", f"{workdir}/{project.name}"
    c.run(
        f"uv export --package {project.name} --frozen --no-dev --no-editable --no-hashes --no-header --quiet -o {reqs}",
        hide=True,
    )
    c.run(f"uv venv --no-project --quiet {venv}", hide=True)
    c.run(f"uv pip install --quiet --python {venv}/bin/python -r {reqs}", hide=True)
    result = c.run(f"{venv}/bin/python -c {shlex.quote(_IMPORT_DISTRIBUTION)} {project.name}", hide=True, warn=True)
    if result.ok:
        return True, f"imports alone ({result.stdout.strip()})"
    if result.exited == _NOT_A_PACKAGE:
        return True, "installs nothing (a virtual project) — skipped"
    lines = result.stderr.strip().splitlines()
    return False, f"FAILS alone — {lines[-1] if lines else f'exit {result.exited}'}"


@requires(NETWORK)
@task(name="check-isolated", help={"project": "Project to check (default: every python project in the repo)"})
def check_isolated(c: Context, project: str | None = None):
    """Install each python project with only what it declares, into a clean venv, and import it —
    exits nonzero naming any that cannot import alone.

    The failure this catches is invisible everywhere else: a workspace syncs every member into one
    environment, so package A importing sibling B without declaring it works in every local run and
    in CI, then fails for whoever installs A's wheel. Measured 2026-09-26 on a three-package
    fixture: the undeclared edge imported in the shared environment and raised
    `ModuleNotFoundError` alone, and the declared edge imported both ways. The same holds for a
    single-project repo importing a dev-only dependency at import time.

    **The closure comes from the lock**, `uv export --package <name> --no-dev --no-editable`: exactly
    what the project declares, at the versions it locks, with a sibling included as a local path only
    when declared. Chosen over installing a built wheel with the index plus `--find-links`, where an
    unrelated index package sharing a sibling's name could satisfy — or mask — the import.

    It proves import-time edges only. An import inside a function, or a declared dependency's
    private module, passes; that half is an architecture linter's question (see the coupling-checker
    plan). Needs the network for third-party packages; builds only in a temporary directory."""
    if not _LOCK_PATH.exists():
        raise Exit("[dist.check-isolated] no uv.lock — run `inv deps.lock` first; the check installs from it", code=1)
    targets = discover_python_projects(c)
    if project is not None:
        targets = [p for p in targets if p.name == project]
        if not targets:
            raise ValueError(f"no python project found for {project!r}")
    if not targets:
        print(f"[dist.check-isolated] {_NO_PROJECTS}")
        return
    failed: list[str] = []
    with tempfile.TemporaryDirectory(prefix="repo-tasks-isolated-") as workdir:
        for target in targets:
            ok, line = _isolated_import(c, target, workdir)
            print(f"[dist.check-isolated] {target.name}  {line}")
            if not ok:
                failed.append(target.name)
    if failed:
        print(f"[dist.check-isolated] {len(failed)} of {len(targets)} cannot import with only what they declare")
        next_steps(*(f"declare what {name} imports in its own [project] dependencies" for name in failed))
        raise Exit(code=1)


# set_dev is imported for the --dev flag; an explicit collection keeps it from being published a
# second time as dist.set-dev (contributing/task-module-conventions.md).
ns: Collection = Collection(clean, build, publish, list_versions, check_isolated)

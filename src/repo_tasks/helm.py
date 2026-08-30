"""Helm chart lint/package/push tasks. Chart path, registry, and group always come from
projects.discover_helm_charts (repo-tasks.toml's [[helm]] entries) — never hardcoded here, so the
task logic stays identical across every consumer repo. The packaged .tgz is named by helm itself
from Chart.yaml's own name/version, so a [[helm]] entry's `name` must match Chart.yaml's `name`;
the version fields stay owned by version.py's group bump (contributing/versioning.md) and are
never written or overridden here."""

from pathlib import Path

from invoke import Collection, Context, task

from .projects import discover_helm_charts
from .requirements import NETWORK, requires
from .version import Version, current_version, set_dev

_CHART_DIST_DIR = Path("dist/helm")

_NO_CHARTS = "no repo-tasks.toml [[helm]] entries — nothing to do"


def _registry_host(registry: str) -> str:
    """The host `helm registry login` has to name, from a chart's oci:// registry reference —
    `oci://ghcr.io/org/charts` is pushed to, `ghcr.io` is logged in to."""
    return registry.removeprefix("oci://").split("/", 1)[0]


def _resolve_chart(c: Context, project: str | None):
    """The chart to act on, or None when the repo has no charts at all — tasks no-op cleanly on
    None (a chartless repo is a normal state), but an explicit --project naming nothing is an
    error, never a guess."""
    charts = discover_helm_charts(c)
    if project is not None:
        charts = [ch for ch in charts if ch.name == project]
        if not charts:
            raise ValueError(f"no helm chart found for project {project!r}")
        return charts[0]
    return charts[0] if charts else None


@task(help={"project": "Chart to lint (default: the sole/first discovered chart)"})
def lint(c: Context, project: str | None = None):
    """Run helm lint against a chart. No-ops cleanly in a repo with no [[helm]] entries."""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.lint] {_NO_CHARTS}")
        return
    c.run(f"helm lint {chart.path}", echo=True)


@task(
    help={
        "project": "Chart to package (default: the sole/first discovered chart)",
        "dev": "Package a dev-build version (X.Y.Z-dev.N.gHASH) — rewrites the working tree's version first, "
        "uncommitted",
    }
)
def package(c: Context, project: str | None = None, dev: bool = False):
    """Package a chart into dist/helm/ (helm package). The .tgz's name and version come from
    Chart.yaml itself — version.py's group bump is what writes those fields."""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.package] {_NO_CHARTS}")
        return
    if dev:
        set_dev(c, group=chart.group)
    c.run(f"helm package {chart.path} --destination {_CHART_DIST_DIR}", echo=True)


@requires(NETWORK)
@task(
    help={
        "project": "Chart to push (default: the sole/first discovered chart)",
        "registry": "OCI registry override, oci://-prefixed (default: the [[helm]] entry's own registry)",
        "plain_http": "Talk plain HTTP to the registry — for a local/dev registry serving no TLS",
    }
)
def push(c: Context, project: str | None = None, registry: str | None = None, plain_http: bool = False):
    """Push a packaged chart to an OCI registry (helm push). Pushes
    dist/helm/<name>-<group version>.tgz — run package first; a missing .tgz (not packaged, or
    Chart.yaml's version disagreeing with the group's) fails loudly rather than pushing the
    wrong thing.

    `--plain-http` has no equivalent of docker's automatic 127.0.0.0/8 insecure-registry
    exemption: helm speaks HTTPS to a loopback registry like any other and fails with "server
    gave HTTP response to HTTPS client", so a local registry needs the flag stated explicitly.
    Off by default — a real registry always serves TLS, and silently downgrading to plain HTTP
    is not something a push task should decide on its own."""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.push] {_NO_CHARTS}")
        return
    resolved_registry = registry or chart.registry
    if resolved_registry is None:
        raise ValueError(f"chart {chart.name!r} has no registry — set one on its [[helm]] entry or pass --registry")
    # Chart.yaml holds the SemVer spelling, so that is what helm named the archive after.
    version = Version.parse(current_version(c, group=chart.group)).semver()
    cmd = f"helm push {_CHART_DIST_DIR / f'{chart.name}-{version}.tgz'} {resolved_registry}"
    if plain_http:
        cmd += " --plain-http"
    c.run(cmd, echo=True)


@requires(NETWORK)
@task(
    help={
        "project": "Chart whose registry to log in to (default: the sole/first discovered chart)",
        "registry": "OCI registry override, oci://-prefixed (default: the [[helm]] entry's own registry)",
    }
)
def login(c: Context, project: str | None = None, registry: str | None = None):
    """Log in to the OCI registry a chart pushes to (helm registry login), prompting for the
    credentials.

    Like docker.login, nothing here reads, stores, forwards or echoes a credential — helm prompts
    and writes the result itself. The registry host comes from repo-tasks.toml rather than being
    retyped. Runs under a pty so helm can prompt. No-ops cleanly in a repo with no [[helm]]
    entries.

    helm stores this in its own registry config, but that config honours a `credsStore` exactly as
    docker's does — helm resolves credentials through oras, whose store checks `credHelpers`, then
    `credsStore`, then a detected platform default. So the credential reaches the OS secret store
    wherever the machine has a credential helper installed.

    Reading is wider than writing: helm searches its own config **and** falls back to
    `~/.docker/config.json`, keyed by registry host. A chart registry on the same host as an image
    registry is therefore already covered by `docker.login`, and this task is what a chart registry
    on its own host needs.

    [UNVERIFIED: that any of this reaches the keyring on this machine, which currently has no
    credential helper installed — see plans/2026-08-30-registry-credentials-in-the-os-store.md,
    blocked on the machine setup that installs one.]"""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.login] {_NO_CHARTS}")
        return
    resolved_registry = registry or chart.registry
    if resolved_registry is None:
        raise ValueError(f"chart {chart.name!r} has no registry — set one on its [[helm]] entry or pass --registry")
    c.run(f"helm registry login {_registry_host(resolved_registry)}", echo=True, pty=True)


# set_dev is imported for the --dev flag; an explicit collection keeps it from being published a
# second time as helm.set-dev (contributing/task-module-conventions.md).
ns = Collection(lint, package, push, login)

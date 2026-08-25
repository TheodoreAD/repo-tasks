"""Helm chart lint/package/push tasks. Chart path, registry, and group always come from
projects.discover_helm_charts (repo-tasks.toml's [[helm]] entries) — never hardcoded here, so the
task logic stays identical across every consumer repo. The packaged .tgz is named by helm itself
from Chart.yaml's own name/version, so a [[helm]] entry's `name` must match Chart.yaml's `name`;
the version fields stay owned by version.py's group bump (contributing/versioning.md) and are
never written or overridden here."""

from pathlib import Path

from invoke import Context, task

from .projects import discover_helm_charts
from .version import current_version

_CHART_DIST_DIR = Path("dist/helm")

_NO_CHARTS = "no repo-tasks.toml [[helm]] entries — nothing to do"


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


@task(help={"project": "Chart to package (default: the sole/first discovered chart)"})
def package(c: Context, project: str | None = None):
    """Package a chart into dist/helm/ (helm package). The .tgz's name and version come from
    Chart.yaml itself — version.py's group bump is what writes those fields."""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.package] {_NO_CHARTS}")
        return
    c.run(f"helm package {chart.path} --destination {_CHART_DIST_DIR}", echo=True)


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
    version = current_version(c, group=chart.group)
    cmd = f"helm push {_CHART_DIST_DIR / f'{chart.name}-{version}.tgz'} {resolved_registry}"
    if plain_http:
        cmd += " --plain-http"
    c.run(cmd, echo=True)

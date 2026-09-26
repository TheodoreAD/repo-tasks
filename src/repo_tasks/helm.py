"""Helm chart lint/package/push tasks. Chart path, registry, and group always come from
projects.discover_helm_charts (repo-tasks.toml's [[helm]] entries) — never hardcoded here, so the
task logic stays identical across every consumer repo. The packaged .tgz is named by helm itself
from Chart.yaml's own name/version, so a [[helm]] entry's `name` must match Chart.yaml's `name`;
the version fields stay owned by version.py's group bump (contributing/versioning.md) and are
never written or overridden here."""

from pathlib import Path

from invoke import Collection, Context, task

from .docker import registry_host as docker_registry_host
from .interactive import run_interactive
from .nextsteps import next_steps
from .projects import HelmChart, discover_docker_images, discover_helm_charts
from .requirements import NETWORK, requires
from .version import Version, current_version, set_dev

_CHART_DIST_DIR = Path("dist/helm")

_NO_CHARTS = "no repo-tasks.toml [[helm]] entries — nothing to do"


def _registry_host(registry: str) -> str:
    """The host `helm registry login` has to name, from a chart's oci:// registry reference —
    `oci://ghcr.io/org/charts` is pushed to, `ghcr.io` is logged in to."""
    return registry.removeprefix("oci://").split("/", 1)[0]


def _images_sharing(c: Context, host: str) -> list[str]:
    """The [[docker]] entries that push to `host`, by name — the case where one login covers both
    tools and one logout ends both.

    Two independent routes make it so, both measured 2026-09-26 against a local htpasswd registry.
    helm reads `~/.docker/config.json` as a fallback, which a helm config pinned to a plain file
    store still honoured. And where both configs name the same `credsStore`, as this machine's do,
    the keyring holds one entry per host that both tools read and either tool's logout erases."""
    return [image.name for image in discover_docker_images(c) if docker_registry_host(image.image) == host]


def _resolve_chart(c: Context, project: str | None) -> HelmChart | None:
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
    retyped. Runs as a plain subprocess with the real terminal attached, for the reasons
    `interactive.py` gives. No-ops cleanly in a repo with no [[helm]] entries.

    helm stores this in its own registry config, but that config honours a `credsStore` exactly as
    docker's does — helm resolves credentials through oras, whose store checks `credHelpers`, then
    `credsStore`, then a detected platform default. So the credential reaches the OS secret store
    wherever the machine has a credential helper installed.

    A chart registry on the same host as a [[docker]] entry is already covered by `docker.login`,
    and this says so before prompting — see `_images_sharing` for the two routes. It still logs in:
    the hint informs, and a second login to the same host is harmless.

    Verified 2026-09-26 against a local htpasswd `registry:2`, a host no docker credential covers:
    the login landed in the OS keyring, helm's own config got an explicit `credsStore` and no
    `auths` entry, a push authenticated from the keyring, and the same push failed after logout."""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.login] {_NO_CHARTS}")
        return
    resolved_registry = registry or chart.registry
    if resolved_registry is None:
        raise ValueError(f"chart {chart.name!r} has no registry — set one on its [[helm]] entry or pass --registry")
    host = _registry_host(resolved_registry)
    if sharing := _images_sharing(c, host):
        print(
            f"[helm.login] {host} is also where {', '.join(sharing)} pushes, so `inv docker.login` already "
            "covers helm there — helm reads docker's credentials for the same host. Logging in anyway."
        )
    run_interactive(f"helm registry login {host}")


@task(
    help={
        "project": "Chart whose registry to log out of (default: the sole/first discovered chart)",
        "registry": "OCI registry override, oci://-prefixed (default: the [[helm]] entry's own registry)",
    }
)
def logout(c: Context, project: str | None = None, registry: str | None = None):
    """Remove the credential `helm.login` stored for a chart's registry (helm registry logout).

    Erases it from helm's own store — the OS secret store where its registry config names a
    `credsStore`, which oras writes there on first login when a helper is installed. **Local only:
    it does not revoke the token**, which happens where it was issued.

    **On a host a [[docker]] entry also uses, one tool's logout is not enough, and says so.** helm
    falls back to docker's credential, so it can keep authenticating after this; and where both
    configs name the same `credsStore` the keyring entry is shared, so this also erases docker's and
    leaves `~/.docker/config.json` a secretless `auths` entry pointing at nothing — measured, see
    `_images_sharing`. Which of the two applies depends on machine config this does not read, and
    `inv docker.logout` is the right next step in both.

    helm prints "Removing login credentials" and exits 0 whether or not a credential was there, so
    that line is not evidence one existed. Nothing is prompted, so this runs through `c.run`."""
    chart = _resolve_chart(c, project)
    if chart is None:
        print(f"[helm.logout] {_NO_CHARTS}")
        return
    resolved_registry = registry or chart.registry
    if resolved_registry is None:
        raise ValueError(f"chart {chart.name!r} has no registry — set one on its [[helm]] entry or pass --registry")
    host = _registry_host(resolved_registry)
    c.run(f"helm registry logout {host}", echo=True)
    if sharing := _images_sharing(c, host):
        print(
            f"[helm.logout] {host} is also where {', '.join(sharing)} pushes. helm can still authenticate "
            "there through docker's credential, and if both tools share a keyring entry this logout "
            "removed docker's too — either way, log docker out as well."
        )
        next_steps("inv docker.logout")


# set_dev is imported for the --dev flag; an explicit collection keeps it from being published a
# second time as helm.set-dev (contributing/task-module-conventions.md).
ns: Collection = Collection(lint, package, push, login, logout)

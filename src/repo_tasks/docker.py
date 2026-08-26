"""Docker image build/push/release tasks. Registry, image name, and Dockerfile path always come
from projects.discover_docker_images (repo-tasks.toml's [[docker]] entries, or the zero-config
Dockerfile-at-root default) — never hardcoded here, so the task logic stays identical across every
consumer repo even though image names/registries legitimately differ per repo."""

from invoke import Collection, Context, task

from .projects import discover_docker_images
from .requirements import DOCKER, requires
from .version import Version, current_version, set_dev

_NO_IMAGES = "no repo-tasks.toml [[docker]] entries and no root Dockerfile — nothing to do"


def _resolve_image(c: Context, project: str | None):
    """The image to act on, or None when the repo has no images at all — tasks no-op cleanly on
    None (an imageless repo is a normal state, so a composite can wire these unconditionally), but
    an explicit --project naming nothing is an error, never a guess. Same shape as helm.py."""
    images = discover_docker_images(c)
    if project is not None:
        images = [i for i in images if i.name == project]
        if not images:
            raise ValueError(f"no docker image found for project {project!r}")
        return images[0]
    return images[0] if images else None


@requires(DOCKER)
@task(
    help={
        "project": "Image to build (default: the sole/first discovered image)",
        "tag": "Tag override (default: the image's group's current version)",
        "platforms": "Comma-separated platform list (e.g. linux/amd64,linux/arm64) — opts into "
        "docker buildx, which pushes as part of build itself (no separate push step for this path)",
        "dev": "Build a dev-build tag (X.Y.Z-dev.N.gHASH) — rewrites the working tree's version first, uncommitted",
    }
)
def build(
    c: Context, project: str | None = None, tag: str | None = None, platforms: str | None = None, dev: bool = False
):
    """Build a docker image (docker build, or docker buildx build --push when platforms is
    given — buildx can't --load a multi-platform result into local docker images). The default
    tag is the group's version in its SemVer spelling (`1.1.0-rc.1` for `1.1.0rc1`). No-ops
    cleanly in a repo with no images."""
    image = _resolve_image(c, project)
    if image is None:
        print(f"[docker.build] {_NO_IMAGES}")
        return
    if dev:
        set_dev(c, group=image.group)
    resolved_tag = tag or Version.parse(current_version(c, group=image.group)).semver()
    target = f"{image.image}:{resolved_tag}"
    if platforms:
        cmd = f"docker buildx build --platform {platforms} -t {target} -f {image.dockerfile} {image.path} --push"
    else:
        cmd = f"docker build -t {target} -f {image.dockerfile} {image.path}"
    c.run(cmd, echo=True)


@requires(DOCKER)
@task(help={"project": "Image to check (default: every discovered image)"})
def check(c: Context, project: str | None = None):
    """Run BuildKit's own build checks (`docker build --check`) over each discovered image's
    Dockerfile — build semantics and casing rules hadolint does not look at: `FromAsCasing`,
    `StageNameCasing`, `LegacyKeyValueFormat`, `UndefinedVar`, `CopyIgnoredFile`,
    `SecretsUsedInArgOrEnv`. It resolves base-image metadata and evaluates the build graph, so it
    needs a reachable Docker daemon and the network behind it.

    That is why this is standalone and hadolint is the gate step, rather than either replacing the
    other: `quality.dockerfile-check` has to run offline in every consumer, and this cannot.
    tests/integration/ is what runs it against this repo's own images.

    No-ops cleanly in a repo with no images. `--check` builds nothing and writes no image; it
    reports the findings and exits non-zero if there are any."""
    if project is None:
        # Every image, unlike build/push/release, which act on one. Checking is cheap and reporting
        # only the first repo's findings would be a check that quietly ignores half the repo.
        images = discover_docker_images(c)
    else:
        one = _resolve_image(c, project)
        images = [one] if one is not None else []
    if not images:
        print(f"[docker.check] {_NO_IMAGES}")
        return
    for image in images:
        c.run(f"docker build --check -f {image.dockerfile} {image.path}", echo=True)


@requires(DOCKER)
@task(
    help={
        "project": "Image to push (default: the sole/first discovered image)",
        "tag": "Tag override (default: the image's group's current version)",
    }
)
def push(c: Context, project: str | None = None, tag: str | None = None):
    """Push a docker image (docker push). Single-arch path only — a multi-platform build already
    pushed as part of build itself. No-ops cleanly in a repo with no images."""
    image = _resolve_image(c, project)
    if image is None:
        print(f"[docker.push] {_NO_IMAGES}")
        return
    resolved_tag = tag or Version.parse(current_version(c, group=image.group)).semver()
    c.run(f"docker push {image.image}:{resolved_tag}", echo=True)


@requires(DOCKER)
@task(help={"project": "Image to release (default: the sole/first discovered image)"})
def release(c: Context, project: str | None = None):
    """Build and push an image tagged with its group's current version — plus `latest`, for a
    final version only: a pre-release (rc or dev build) is opt-in for whoever pulls it, the same
    way helm and pip treat theirs, and `latest` is the one tag that opts everyone in. No-ops
    cleanly, as one unit, in a repo with no images."""
    image = _resolve_image(c, project)
    if image is None:
        print(f"[docker.release] {_NO_IMAGES}")
        return
    version = Version.parse(current_version(c, group=image.group))
    tag = version.semver()
    build(c, project=project, tag=tag)
    push(c, project=project, tag=tag)
    if not version.is_final:
        print(f"[docker.release] {tag} is a pre-release — not tagged latest")
        return
    c.run(f"docker tag {image.image}:{tag} {image.image}:latest", echo=True)
    push(c, project=project, tag="latest")


# set_dev is imported for the --dev flag; an explicit collection keeps it from being published a
# second time as docker.set-dev (contributing/task-module-conventions.md).
ns = Collection(check, build, push, release)

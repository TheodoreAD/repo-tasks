"""Docker image build/push/release tasks. Registry, image name, and Dockerfile path always come
from projects.discover_docker_images (repo-tasks.toml's [[docker]] entries, or the zero-config
Dockerfile-at-root default) — never hardcoded here, so the task logic stays identical across every
consumer repo even though image names/registries legitimately differ per repo."""

from invoke import task

from .projects import discover_docker_images
from .version import current_version


def _resolve_image(c, project):
    images = discover_docker_images(c)
    if project is not None:
        images = [i for i in images if i.name == project]
        if not images:
            raise ValueError(f"no docker image found for project {project!r}")
        return images[0]
    if not images:
        raise ValueError("no docker image found (no repo-tasks.toml [[docker]] entries and no root Dockerfile)")
    return images[0]


@task(
    help={
        "project": "Image to build (default: the sole/first discovered image)",
        "tag": "Tag override (default: the image's group's current version)",
        "platforms": "Comma-separated platform list (e.g. linux/amd64,linux/arm64) — opts into "
        "docker buildx, which pushes as part of build itself (no separate push step for this path)",
    }
)
def build(c, project=None, tag=None, platforms=None):
    """Build a docker image (docker build, or docker buildx build --push when platforms is
    given — buildx can't --load a multi-platform result into local docker images)."""
    image = _resolve_image(c, project)
    resolved_tag = tag or current_version(c, group=image.group)
    target = f"{image.image}:{resolved_tag}"
    if platforms:
        cmd = f"docker buildx build --platform {platforms} -t {target} -f {image.dockerfile} {image.path} --push"
    else:
        cmd = f"docker build -t {target} -f {image.dockerfile} {image.path}"
    c.run(cmd, echo=True)


@task(
    help={
        "project": "Image to push (default: the sole/first discovered image)",
        "tag": "Tag override (default: the image's group's current version)",
    }
)
def push(c, project=None, tag=None):
    """Push a docker image (docker push). Single-arch path only — a multi-platform build already
    pushed as part of build itself."""
    image = _resolve_image(c, project)
    resolved_tag = tag or current_version(c, group=image.group)
    c.run(f"docker push {image.image}:{resolved_tag}", echo=True)


@task(help={"project": "Image to release (default: the sole/first discovered image)"})
def release(c, project=None):
    """Build and push an image tagged with its group's current version, plus latest."""
    image = _resolve_image(c, project)
    tag = current_version(c, group=image.group)
    build(c, project=project, tag=tag)
    c.run(f"docker tag {image.image}:{tag} {image.image}:latest", echo=True)
    push(c, project=project, tag=tag)
    push(c, project=project, tag="latest")

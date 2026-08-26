# Minimal, non-root environment for testing repo-tasks' own user-wide effects (selfinstall.py,
# agents.py, direnv.py, configs.py) against a genuinely clean $HOME -- see
# contributing/test-tiers.md's clean-OS section. Deliberately NOT at the repo root:
# projects.discover_docker_images(c) treats a root Dockerfile as this repo's own implicit
# shippable image (see discover_docker_images' own docstring), which this isn't.
FROM debian:bookworm-slim

# DL3008 (pin apt versions) is declined here, not overlooked. Debian's archive keeps exactly one
# version of each package per suite, so a pinned `curl=8.x.y-z` stops resolving the week bookworm
# takes a point release -- the rule buys reproducibility for an image with its own apt mirror, and
# costs a fixture build that breaks on someone else's release schedule. This image is rebuilt from
# scratch by the integration tier and ships nowhere.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git direnv \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash tester
# The numeric-USER rule is about an orchestrator resolving the uid at admission time; nothing runs
# this image but testcontainers, and the tests address the user by the name of its home directory.
# hadolint ignore=DL3066
USER tester
WORKDIR /home/tester

# pipefail before the piped install, or a failed download still exits 0 through `sh` and the layer
# is committed with no uv in it -- a fixture that silently lacks the tool it exists to provide.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/tester/.local/bin:${PATH}"

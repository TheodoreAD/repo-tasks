# Minimal, non-root environment for testing repo-tasks' own user-wide effects (selfinstall.py,
# agents.py, direnv.py, configs.py) against a genuinely clean $HOME -- see
# contributing/test-tiers.md's clean-OS section. Deliberately NOT at the repo root:
# projects.discover_docker_images(c) treats a root Dockerfile as this repo's own implicit
# shippable image (plans/2026-08-19-monorepo-workspace-foundation.md Design section 2), which this isn't.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git direnv \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash tester
USER tester
WORKDIR /home/tester

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/tester/.local/bin:${PATH}"

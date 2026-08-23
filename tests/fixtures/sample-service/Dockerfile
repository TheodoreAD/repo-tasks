# syntax=docker/dockerfile:1
#
# The multi-stage recipe README's venv/deps section describes, applied to a real workspace member.
# Built from the *repo root* as context, not this directory: a uv workspace member's dependencies
# resolve from the workspace root's own pyproject.toml and uv.lock, so a context scoped to
# this directory could not run `uv sync --locked` at all. repo-tasks.toml's [[docker]]
# entry is what pairs `path = "."` with this dockerfile.
#
# Every build step goes through this repo's own inv tasks rather than hand-written uv commands —
# the whole reason this sample exists is to prove those tasks work against a real image.

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# UV_LINK_MODE=copy: the cache and the venv sit on different layers, where uv's default hardlink
# strategy can't work. UV_COMPILE_BYTECODE=1 pays the .pyc cost once at build time instead of on
# every container's first request.
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/root/.local/bin:$PATH \
    VIRTUAL_ENV=/app/.venv

WORKDIR /app

# repo-tasks installed from the source in this build context, never from its git URL: an image
# build must not depend on the upstream remote's tags or on network reachability. Same call, and
# same reason, as tests/integration/'s clean-OS fixture.
RUN --mount=type=bind,source=.,target=/src,ro \
    uv tool install --with-executables-from invoke /src

# Deps-only layer, keyed on just the workspace manifests and the lock — every commit that touches
# none of them reuses it. --no-install-project keeps the member's own code out, so editing the
# service never invalidates its dependency install. tasks.py is mounted alongside them because
# bare `inv` refuses to run without a collection to load, and it can't be pointed at an installed
# package's submodule instead (see src/repo_tasks/cli.py's docstring).
RUN --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=tasks.py,target=tasks.py \
    --mount=type=bind,source=tests/fixtures/sample-service/pyproject.toml,target=tests/fixtures/sample-service/pyproject.toml \
    inv venv.sync --project sample-service --no-dev --no-install-project

# The member's own wheel on top of that cached layer. install_wheel is `uv pip install --no-deps`,
# so nothing here can re-resolve or quietly upgrade what the layer above installed — the container
# runs exactly the wheel `inv dist.publish` would have uploaded.
COPY . /app
RUN inv dist.build --project sample-service && inv venv.install-wheel

# The runtime stage carries no source tree, no uv, and no repo-tasks — only the venv. It stays at
# /app/.venv because a virtualenv's scripts hardcode their own absolute path; relocating it would
# break every console script inside.
FROM python:3.13-slim-bookworm AS runtime

RUN useradd --create-home --uid 10001 app
COPY --from=builder --chown=app:app /app/.venv /app/.venv

USER app
ENV PATH=/app/.venv/bin:$PATH \
    PORT=8000
EXPOSE 8000

# Exec form, so the service is PID 1 and receives SIGTERM directly — no shell swallowing it, which
# is what turns a graceful pod shutdown into a 30-second kill.
CMD ["sample-service"]

"""The quality gate, run on a machine that has none of the tools it shells out to.

Everything else in this tier covers repo-tasks' *user-wide effects* — installing itself, direnv,
the Claude hook. Nothing covered the gate, which is the thing every consumer actually runs, and the
gap was not neutral: measured on the dev machine 2026-09-06 with the project venv taken off PATH,
four of the eight gate binaries (`dprint`, `shellcheck`, `shfmt`, `actionlint`) still resolved from
`~/.local/bin`, installed there by a sibling repo. So the machine where the gate is written can pass
it for reasons a fresh consumer does not have, and `configs.require_tool` — the preflight built for
exactly that drift — cannot fire for those four here however stale a consumer's dev group is.

This module is the other side of that: a container with `uv`, `git` and `direnv` and nothing else,
where the only way a gate binary can exist is the project's own dependency group.

Its own container, not the one `test_clean_os_user_effects.py` shares: `uv sync` here materialises a
`.venv` inside the repo copy and every gate step then reads it, which is not the disjoint-paths
property that module's fixture scope depends on.
"""

import pytest
from testcontainers.core.container import DockerContainer

_HOME = "/home/tester"
_REPO = f"{_HOME}/repo-tasks"

# Every binary a gate step shells out to — `configs._GATE_TOOL_DISTRIBUTIONS`' keys minus `pytest`,
# which the gate runs through `testing.py` rather than as a bare command. Asserted absent before the
# sync and exercised after it.
_GATE_BINARIES = ("ruff", "dprint", "basedpyright", "shellcheck", "shfmt", "actionlint", "zizmor", "hadolint")

# The binary-dependent half of `quality.check`, run as its own composite rather than `check` itself.
# `check` would also run `deps.check`, `link_check`, `untested_modules` and the whole unit suite
# inside the container — minutes of runtime that re-tests what the unit tier already covers, and a
# flake surface with nothing to say about the question this module asks.
_TOOL_STEPS = (
    "quality.lint-check quality.format-check quality.type-check "
    "quality.shell-check quality.shell-format-check quality.workflow-check quality.dockerfile-check"
)


def _run(container: DockerContainer, script: str) -> tuple[int | None, str]:
    result = container.exec(["bash", "-c", script])
    return result.exit_code, result.output.decode()


@pytest.fixture(scope="module")
def synced_repo(clean_os_container: DockerContainer) -> DockerContainer:
    """The repo's own dev group installed into a project venv, on a machine that started with none
    of the gate binaries — which is what a fresh consumer is.

    The absence check runs first and is the load-bearing half: without it the gate run below would
    pass just as happily on a machine that had the tools all along, which is precisely the state
    that hid this gap on the machine where the code is written."""
    for tool in _GATE_BINARIES:
        exit_code, output = _run(clean_os_container, f"command -v {tool}")
        assert exit_code != 0, f"{tool} is already on PATH — this is not a clean machine: {output}"

    exit_code, output = _run(clean_os_container, f"cd {_REPO} && uv sync --group dev")
    assert exit_code == 0, output
    return clean_os_container


def test_the_dev_group_supplies_every_gate_binary(synced_repo: DockerContainer):
    """What `configs.require_tool` asserts a consumer can rely on, checked where nothing else could
    be providing them. A binary missing here is a manifest that does not deliver what the gate
    assumes, and no amount of `require_tool` messaging fixes that."""
    for tool in _GATE_BINARIES:
        exit_code, output = _run(synced_repo, f"test -x {_REPO}/.venv/bin/{tool}")
        assert exit_code == 0, f"{tool} is not in the project venv after `uv sync --group dev`: {output}"


def test_the_gate_runs_where_none_of_its_tools_were_installed(synced_repo: DockerContainer):
    """The gate's binary-dependent steps, green, with `.venv/bin` on PATH the way direnv puts it
    there locally and `venv.create`'s GITHUB_PATH registration puts it there in CI.

    This is also the only place dprint's plugin fetch is exercised cold. Its five formatting plugins
    are remote `.wasm` URLs cached under `~/.cache/dprint`, so on the dev machine — whose cache
    predates this gate — the download has never once run. Here the cache starts empty, which makes
    this the one test that would notice a bad `@<sha256>` in the shipped `dprint.json`."""
    exit_code, output = _run(synced_repo, f"cd {_REPO} && PATH={_REPO}/.venv/bin:$PATH inv {_TOOL_STEPS}")
    assert exit_code == 0, output

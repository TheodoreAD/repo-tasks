"""Real mutating tests for repo-tasks' user-wide-effects tasks, run inside clean_os_container's
isolated non-root $HOME — see contributing/test-tiers.md's clean-OS section. Unit tests
(tests/test_agents.py etc.) already cover the pure filesystem/JSON logic against tmp_path; what
only this tier can cover is the real daily-driver shape: selfinstall's actual `uv tool install`
command producing a working global `inv` on a machine with no Python at all, that `inv` resolving
a consumer repo's tasks.py, and the real `direnv` binary's allow state — all strictly under a
non-root user's own $HOME.

Fixture-scope decision: these tests deliberately share one module-scoped container. Isolation
holds because pytest instantiates a module-scoped fixture once per *module* — the smoke-test
module gets its own container, untouched by these mutations —
and because every mutation here lands on a disjoint path: the tool install under ~/.local/bin and
~/.local/share/uv (a fixture, so nothing depends on test file-order), direnv's allow database under
~/.local/share/direnv, claude-hook's output in its own scratch project dir plus
~/.cache/claude-code. A future test that can't keep that disjoint-paths property belongs in a
function-scoped container of its own, not in this module."""

import json
from pathlib import Path
from typing import cast

import pytest
from testcontainers.core.container import DockerContainer

from repo_tasks import agents
from repo_tasks.selfinstall import _INSTALL_CMD  # pyright: ignore[reportPrivateUsage]

_HOME = "/home/tester"
_REPO = f"{_HOME}/repo-tasks"


def _run(container: DockerContainer, script: str) -> tuple[int | None, str]:
    """exit_code is `int | None` in testcontainers' own return type, not `int` — surfaced the
    first time this tier was type-checked. Left as-is rather than coerced: a None exit code is a
    real state (the command never produced one) and callers assert `== 0`, which None fails."""
    result = container.exec(["bash", "-c", script])
    return result.exit_code, result.output.decode()


@pytest.fixture(scope="module")
def installed_repo_tasks(clean_os_container: DockerContainer) -> DockerContainer:
    """repo-tasks installed as the global daily-driver uv tool via selfinstall.py's real
    _INSTALL_CMD — pointed at the container's own source copy instead of the GitHub URL update()
    would install from, so the test exercises the exact command shape without depending on the
    real remote's network or tags."""
    exit_code, output = _run(clean_os_container, f"{_INSTALL_CMD} {_REPO}")
    assert exit_code == 0, output
    return clean_os_container


def test_install_exposes_inv_on_user_path(installed_repo_tasks: DockerContainer):
    """The load-bearing selfinstall claim (see its module docstring): --with-executables-from
    invoke is the only reason `inv` lands on PATH at all — and it must land under the non-root
    user's own ~/.local/bin, never anywhere root-owned."""
    exit_code, output = _run(installed_repo_tasks, "command -v inv")
    assert exit_code == 0, output
    assert output.strip() == f"{_HOME}/.local/bin/inv"


def test_installed_inv_resolves_consumer_tasks(installed_repo_tasks: DockerContainer):
    """A consumer repo's whole tasks.py is `from repo_tasks import ns` (README) — the installed
    tool's own venv is what that import resolves against, with no project venv existing yet."""
    exit_code, output = _run(installed_repo_tasks, f"cd {_REPO} && inv --list")
    assert exit_code == 0, output
    assert "quality.precommit" in output
    assert "repo-tasks.update" in output


def test_direnv_allow_unblocks_envrc(installed_repo_tasks: DockerContainer):
    exit_code, output = _run(installed_repo_tasks, f"cd {_REPO} && direnv export bash")
    assert exit_code != 0, f"fresh $HOME must start with .envrc blocked, or this proves nothing: {output}"

    exit_code, output = _run(installed_repo_tasks, f"cd {_REPO} && inv direnv.allow")
    assert exit_code == 0, output

    exit_code, output = _run(installed_repo_tasks, f"cd {_REPO} && direnv export bash")
    assert exit_code == 0, output
    assert "VIRTUAL_ENV" in output


def test_claude_hook_wires_clean_home(installed_repo_tasks: DockerContainer):
    """Fresh project dir, fresh $HOME: settings.json created from nothing, and the env cache file
    materialized under the real ~/.cache/claude-code — the path-shape half tests/test_agents.py
    can't cover, since there _claude_env_file_path is exercised against the dev machine's $HOME."""
    project = f"{_HOME}/hooked-project"
    env_file = f"{_HOME}/.cache/claude-code/home-tester-hooked-project-direnv-env"
    exit_code, output = _run(
        installed_repo_tasks,
        f"mkdir -p {project} && touch {project}/.envrc && cd {_REPO} && inv agents.claude-hook --dir {project}",
    )
    assert exit_code == 0, output

    exit_code, output = _run(installed_repo_tasks, f"cat {project}/.claude/settings.json")
    assert exit_code == 0, output
    settings = cast(
        agents._ClaudeSettings,  # pyright: ignore[reportPrivateUsage]
        json.loads(output),
    )
    assert settings.get("env", {}).get("CLAUDE_ENV_FILE") == env_file
    bash_group = next(g for g in settings.get("hooks", {}).get("PreToolUse", []) if g["matcher"] == "Bash")
    expected_command = agents._direnv_hook_command(Path(env_file))  # pyright: ignore[reportPrivateUsage]
    assert bash_group["hooks"][0]["command"] == expected_command

    exit_code, output = _run(installed_repo_tasks, f"test -f {env_file}")
    assert exit_code == 0, output

"""Tests for repo_tasks.dev_env: setup is pure orchestration (pre=[venv.create, direnv.allow,
agents.claude_hook]) with no logic of its own to unit test beyond that wiring — covered by
test_init.py's collection-shape check plus each real task's own module tests."""

from repo_tasks import agents, dev_env, direnv, venv


def test_setup_composes_venv_direnv_and_agents_hook():
    assert dev_env.setup.pre == [venv.create, direnv.allow, agents.claude_hook]  # pyright: ignore[reportAny, reportFunctionMemberAccess]

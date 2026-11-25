"""Tests for repo_tasks.dev_env: setup is pure orchestration (pre=[venv.create, direnv.allow,
agents.wire_claude_hook, agents.install_skills]) with no logic of its own to unit test beyond that
wiring — covered by test_init.py's collection-shape check plus each real task's own module tests."""

from repo_tasks import agents, dev_env, direnv, venv


def test_setup_composes_venv_direnv_agents_hook_and_skills():
    assert dev_env.setup.pre == [venv.create, direnv.allow, agents.wire_claude_hook, agents.install_skills]

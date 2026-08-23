"""Tests for repo_tasks.configure: configure is pure orchestration (pre=[dev_env.setup,
configs.pull, selfinstall.stamp]) with no logic of its own — same shape as test_dev_env.py's own
composition test."""

from repo_tasks import configs, configure, dev_env, selfinstall


def test_configure_composes_dev_env_setup_configs_pull_and_selfinstall_stamp():
    assert configure.configure.pre == [dev_env.setup, configs.pull, selfinstall.stamp]  # pyright: ignore[reportAny, reportFunctionMemberAccess]

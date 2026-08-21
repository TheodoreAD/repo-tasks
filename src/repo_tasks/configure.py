"""The one command anything outside this package should ever need to name directly — a stable
entrypoint that survives this package's own internal module reshuffling. Owns no logic of its
own, same allowance dev_env.py already has for the same reason."""

from invoke import task

from .configs import pull as configs_pull
from .dev_env import setup as dev_env_setup


@task(pre=[dev_env_setup, configs_pull])
def configure(c):
    """Run once after cloning or generating a repo from scratch: dev-env setup (venv, direnv,
    Claude Code hook) plus pulling the canonical tool configs. The one command a fresh checkout
    needs before anything else works."""

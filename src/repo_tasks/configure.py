"""The one command anything outside this package should ever need to name directly — a stable
entrypoint that survives this package's own internal module reshuffling. Owns no logic of its
own, same allowance dev_env.py already has for the same reason."""

from invoke import Context, task

from .configs import pull as configs_pull
from .dev_env import setup as dev_env_setup
from .selfinstall import stamp as selfinstall_stamp


@task(pre=[dev_env_setup, configs_pull, selfinstall_stamp])
def configure(c: Context):
    """Run once after cloning or generating a repo from scratch: dev-env setup (venv, direnv,
    Claude Code hook), pulling the canonical tool configs, and stamping bootstrap-repo-tasks.sh
    with the currently-active repo-tasks version (CI/reproducibility archaeology, see
    selfinstall.py). The one command a fresh checkout needs before anything else works."""

"""Post-clone dev-environment bootstrap: wires venv, direnv, and the Claude Code agent hook
together into the one command to run after cloning. Owns no logic of its own — each concern's
real implementation lives in its own module (venv.py, direnv.py, agents.py)."""

from invoke import task

import repo_tasks.agents as agents
import repo_tasks.direnv as direnv
import repo_tasks.venv as venv_module


@task(pre=[venv_module.create, direnv.allow, agents.claude_hook])
def setup(c):
    """Run once after cloning: create/refresh .venv, let direnv auto-activate it, and wire
    Claude Code's Bash tool to auto-activate it too. The one command to run before anything else."""

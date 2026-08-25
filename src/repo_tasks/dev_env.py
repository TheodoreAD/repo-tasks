"""Post-clone dev-environment bootstrap: wires venv, direnv, and the Claude Code agent hook
together into the one command to run after cloning. Owns no logic of its own — each concern's
real implementation lives in its own module (venv.py, direnv.py, agents.py)."""

from invoke.collection import Collection
from invoke.context import Context
from invoke.tasks import task

from .agents import wire_claude_hook
from .direnv import allow
from .venv import create


@task(pre=[create, allow, wire_claude_hook])
def setup(c: Context):
    """Run once after cloning: create/refresh .venv, let direnv auto-activate it, and wire
    Claude Code's Bash tool to auto-activate it too. The one command to run before anything else."""


# Explicit namespace, not Collection.from_module's auto-scan: the three imports above exist for
# `setup`'s pre-chain, and the auto-scan republished each of them under a second name
# (`dev-env.create`, `dev-env.allow`, `dev-env.claude-hook`) alongside their real ones in
# venv/direnv/agents. This module deliberately owns exactly one task.
ns = Collection(setup)

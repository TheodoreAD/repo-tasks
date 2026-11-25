"""Post-clone dev-environment bootstrap: wires venv, direnv, the Claude Code agent hook and the
repo's own agent skills together into the one command to run after cloning. Owns no logic of its
own — each concern's real implementation lives in its own module (venv.py, direnv.py, agents.py)."""

from invoke import Collection, Context, task

from .agents import install_skills, wire_claude_hook
from .direnv import allow
from .venv import create


@task(pre=[create, allow, wire_claude_hook, install_skills])
def setup(c: Context):
    """Run once after cloning: create/refresh .venv, let direnv auto-activate it, wire Claude Code's
    Bash tool to auto-activate it too, and install the repo's own skills from skills/ for every
    agent. The one command to run before anything else."""


# Explicit namespace, not Collection.from_module's auto-scan: the imports above exist for `setup`'s
# pre-chain, and the auto-scan republished each of them under a second name (`dev-env.create`,
# `dev-env.allow`, `dev-env.claude-hook`) alongside their real ones in venv/direnv/agents. This
# module deliberately owns exactly one task.
ns: Collection = Collection(setup)

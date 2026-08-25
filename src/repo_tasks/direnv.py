"""direnv facility: idempotent shell auto-activation for this repo's .venv."""

import shutil

from invoke.context import Context
from invoke.tasks import task


def _command_exists(name: str) -> bool:
    return shutil.which(name) is not None


@task
def allow(c: Context):
    """Run `direnv allow` if direnv is installed; no-ops with a message otherwise."""
    if _command_exists("direnv"):
        c.run("direnv allow", echo=True)
    else:
        print("[direnv.allow] direnv not found — skipping shell auto-activation")

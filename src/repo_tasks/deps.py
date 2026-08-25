"""Dependency lock-file operations. The only module in this package allowed to write uv.lock —
`venv.py`'s `--locked` sync fails loudly on drift instead of ever silently regenerating it."""

import re

from invoke import Context, Exit, task

# Underscored to stay out of gitflow's CLI namespace, not out of sibling modules.
from .gitflow import _next_steps  # pyright: ignore[reportPrivateUsage]

# The one `uv lock` failure a plain re-run never fixes: a workspace member that *moved*. uv.lock
# records the member's `source = { editable = "<old path>" }` and uv reads that stale entry before
# noticing the manifest changed, so both `uv lock` and `uv lock --check` fail with this message
# (exit 2), naming a path that no longer exists. `--upgrade-package <member>` re-resolves it.
# Measured against uv 0.11.19: renaming a member (path unchanged) or removing it outright both
# re-resolve fine — only a move does this.
_MOVED_MEMBER_RE = re.compile(r"Failed to generate package metadata for `(?P<name>[^=` ]+)[^`]*@ editable\+")


@task(
    help={
        "upgrade": "Fully re-resolve every dependency",
        "package": "Upgrade one package deliberately (--upgrade-package)",
    }
)
def lock(c: Context, upgrade: bool = False, package: str | None = None):
    """Write/update uv.lock. The only task in this package that ever runs `uv lock`."""
    cmd = "uv lock"
    if upgrade:
        cmd += " --upgrade"
    if package:
        cmd += f" --upgrade-package {package}"
    result = c.run(cmd, echo=True, warn=True)
    if result.ok:
        return
    match = _MOVED_MEMBER_RE.search(result.stderr)
    if match:
        print(
            f"\n[deps.lock] workspace member {match.group('name')!r} looks moved — uv.lock still records its old "
            "path, and a plain `uv lock` never re-resolves that."
        )
        _next_steps(f"inv deps.lock --package {match.group('name')}")
    raise Exit(code=result.exited)


@task
def check(c: Context):
    """Check uv.lock is up-to-date with pyproject.toml, read-only, no .venv needed."""
    c.run("uv lock --check", echo=True)


@task(help={"outdated": "Show the latest available version of each installed package"})
def list(c: Context, outdated: bool = False):  # noqa: A001 — this is the CLI task name (`inv deps.list`), matches uv's own `list` verb
    """List what's actually installed in .venv (uv pip list)."""
    cmd = "uv pip list"
    if outdated:
        cmd += " --outdated"
    c.run(cmd, echo=True)


@task(help={"outdated": "Show the latest available version of each package in the tree"})
def tree(c: Context, outdated: bool = False):
    """Show the full resolved dependency tree from uv.lock (uv tree)."""
    cmd = "uv tree"
    if outdated:
        cmd += " --outdated"
    c.run(cmd, echo=True)


@task(help={"output": "Output path for the exported requirements file", "no_dev": "Skip the dev dependency group"})
def export(c: Context, output: str = "requirements.txt", no_dev: bool = False):
    """Export uv.lock to a pinned requirements.txt (--locked, non-editable) for non-uv-aware
    consumers — SBOM/vulnerability scanners, plain-pip CI steps."""
    cmd = "uv export --format requirements.txt --locked --no-editable"
    if no_dev:
        cmd += " --no-dev"
    cmd += f" -o {output}"
    c.run(cmd, echo=True)

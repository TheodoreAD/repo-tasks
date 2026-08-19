"""Dependency lock-file operations. The only module in this package allowed to write uv.lock —
`venv.py`'s `--locked` sync fails loudly on drift instead of ever silently regenerating it."""

from invoke import task


@task(
    help={
        "upgrade": "Fully re-resolve every dependency",
        "package": "Upgrade one package deliberately (--upgrade-package)",
    }
)
def lock(c, upgrade=False, package=None):
    """Write/update uv.lock. The only task in this package that ever runs `uv lock`."""
    cmd = "uv lock"
    if upgrade:
        cmd += " --upgrade"
    if package:
        cmd += f" --upgrade-package {package}"
    c.run(cmd, echo=True)


@task
def check(c):
    """Check uv.lock is up-to-date with pyproject.toml, read-only, no .venv needed."""
    c.run("uv lock --check", echo=True)


@task(help={"outdated": "Show the latest available version of each installed package"})
def list(c, outdated=False):  # noqa: A001 — this is the CLI task name (`inv deps.list`), matches uv's own `list` verb
    """List what's actually installed in .venv (uv pip list)."""
    cmd = "uv pip list"
    if outdated:
        cmd += " --outdated"
    c.run(cmd, echo=True)


@task(help={"outdated": "Show the latest available version of each package in the tree"})
def tree(c, outdated=False):
    """Show the full resolved dependency tree from uv.lock (uv tree)."""
    cmd = "uv tree"
    if outdated:
        cmd += " --outdated"
    c.run(cmd, echo=True)


@task(help={"output": "Output path for the exported requirements file", "no_dev": "Skip the dev dependency group"})
def export(c, output="requirements.txt", no_dev=False):
    """Export uv.lock to a pinned requirements.txt (--locked, non-editable) for non-uv-aware
    consumers — SBOM/vulnerability scanners, plain-pip CI steps."""
    cmd = "uv export --format requirements.txt --locked --no-editable"
    if no_dev:
        cmd += " --no-dev"
    cmd += f" -o {output}"
    c.run(cmd, echo=True)

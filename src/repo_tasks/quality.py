"""Shared, reproducible quality-tooling invoke tasks. Every command is echoed
(echo=True) so both a human and an agent see exactly what ran — the only
exception is a step that would involve a secret, and none here do.

Running tests is not this module's job — that lives in testing.py, under its own `test` namespace
with one task per tier. `check` pulls in only the unit tier from there, since it is the only tier
with no prerequisites beyond the dev dependency group."""

from invoke import task

from .testing import unit


def _sh_files(c):
    result = c.run("git ls-files --cached --others --exclude-standard -- '*.sh'", hide=True, warn=True)
    return result.stdout.split() if result.ok else []


@task
def lint_check(c):
    """Run ruff's linter (no fixes)."""
    c.run("ruff check .", echo=True)


@task
def lint_apply(c):
    """Run ruff's linter and apply auto-fixes."""
    c.run("ruff check --fix .", echo=True)


@task
def format_check(c):
    """Check formatting (ruff format, dprint) without writing changes."""
    c.run("ruff format --check .", echo=True)
    c.run("dprint check --config-discovery=ignore-descendants", echo=True)


@task
def format_apply(c):
    """Apply formatting: ruff format, then dprint fmt."""
    c.run("ruff format .", echo=True)
    c.run("dprint fmt --config-discovery=ignore-descendants", echo=True)


@task
def type_check(c):
    """Run basedpyright's type checker."""
    c.run("basedpyright", echo=True)


@task
def shell_check(c):
    """Run shellcheck against every *.sh file in the repo.

    No-ops cleanly on a repo with no shell scripts, so this is safe to run
    unconditionally in every consumer's `check` — no per-repo opt-out needed.
    """
    files = _sh_files(c)
    if files:
        c.run(f"shellcheck {' '.join(files)}", echo=True)


@task
def shell_format_check(c):
    """Check shell script formatting (shfmt) without writing changes. No-ops
    cleanly on a repo with no shell scripts."""
    files = _sh_files(c)
    if files:
        c.run(f"shfmt -d {' '.join(files)}", echo=True)


@task
def shell_format_apply(c):
    """Apply shell script formatting (shfmt). No-ops cleanly on a repo with
    no shell scripts."""
    files = _sh_files(c)
    if files:
        c.run(f"shfmt -w {' '.join(files)}", echo=True)


@task(pre=[lint_apply, format_apply, shell_format_apply])
def fix(c):
    """Fix everything auto-fixable: ruff --fix, ruff format, dprint fmt, shfmt -w."""


@task(pre=[lint_check, format_check, type_check, shell_check, unit])
def check(c):
    """CI-style gate: every check, no changes written."""


@task(pre=[fix, check])
def precommit(c):
    """Fix, then check — the one command to run before considering a change
    done, with no need to know or invoke the individual tools."""

"""Shared, reproducible quality-tooling invoke tasks. Every command is echoed
(echo=True) so both a human and an agent see exactly what ran — the only
exception is a step that would involve a secret, and none here do.

Running tests is not this module's job — that lives in testing.py, under its own `test` namespace
with one task per tier. `check` pulls in only the unit tier from there, since it is the only tier
with no prerequisites beyond the dev dependency group."""

from invoke import Collection, Context, task

from .configs import require_tool

# Aliased: this module has its own `check`, and the gate needs deps' one in its pre-chain.
from .deps import check as deps_check
from .testing import unit


def _tracked_files(c: Context, *patterns: str):
    """Files matching the git pathspecs — tracked or untracked-but-not-ignored, so a script written
    a moment ago is checked before it is ever `git add`ed. An empty list on any git failure (not a
    repo at all), which every caller treats as "nothing to do"."""
    specs = " ".join(f"'{p}'" for p in patterns)
    result = c.run(f"git ls-files --cached --others --exclude-standard -- {specs}", hide=True, warn=True)
    return result.stdout.split() if result.ok else []


def _sh_files(c: Context):
    return _tracked_files(c, "*.sh")


def _workflow_files(c: Context):
    return _tracked_files(c, ".github/workflows/*.yml", ".github/workflows/*.yaml")


@task
def lint_check(c: Context):
    """Run ruff's linter (no fixes)."""
    require_tool("ruff")
    c.run("ruff check .", echo=True)


@task
def lint_apply(c: Context):
    """Run ruff's linter and apply auto-fixes."""
    require_tool("ruff")
    c.run("ruff check --fix .", echo=True)


@task
def format_check(c: Context):
    """Check formatting (ruff format, dprint) without writing changes."""
    require_tool("ruff")
    require_tool("dprint")
    c.run("ruff format --check .", echo=True)
    c.run("dprint check --config-discovery=ignore-descendants", echo=True)


@task
def format_apply(c: Context):
    """Apply formatting: ruff format, then dprint fmt."""
    require_tool("ruff")
    require_tool("dprint")
    c.run("ruff format .", echo=True)
    c.run("dprint fmt --config-discovery=ignore-descendants", echo=True)


@task
def type_check(c: Context):
    """Run basedpyright's type checker."""
    require_tool("basedpyright")
    c.run("basedpyright", echo=True)


@task
def shell_check(c: Context):
    """Run shellcheck against every *.sh file in the repo.

    No-ops cleanly on a repo with no shell scripts, so this is safe to run
    unconditionally in every consumer's `check` — no per-repo opt-out needed.
    """
    files = _sh_files(c)
    if files:
        # Inside the branch, never above it: preflighting unconditionally would turn "this repo has
        # no shell scripts" into a hard failure and cost the no-op contract the docstring promises.
        # Same in every file-gated step below.
        require_tool("shellcheck")
        c.run(f"shellcheck {' '.join(files)}", echo=True)


@task
def shell_format_check(c: Context):
    """Check shell script formatting (shfmt) without writing changes. No-ops
    cleanly on a repo with no shell scripts."""
    files = _sh_files(c)
    if files:
        require_tool("shfmt")
        c.run(f"shfmt -d {' '.join(files)}", echo=True)


@task
def shell_format_apply(c: Context):
    """Apply shell script formatting (shfmt). No-ops cleanly on a repo with
    no shell scripts."""
    files = _sh_files(c)
    if files:
        require_tool("shfmt")
        c.run(f"shfmt -w {' '.join(files)}", echo=True)


@task
def workflow_check(c: Context):
    """Run actionlint against every GitHub Actions workflow file (.github/workflows/*.yml). No-ops
    cleanly on a repo with no workflows, so it is safe in every consumer's `check`."""
    files = _workflow_files(c)
    if files:
        require_tool("actionlint")
        c.run(f"actionlint {' '.join(files)}", echo=True)


@task(pre=[lint_apply, format_apply, shell_format_apply])
def fix(c: Context):
    """Fix everything auto-fixable: ruff --fix, ruff format, dprint fmt, shfmt -w."""


@task(pre=[lint_check, format_check, type_check, shell_check, shell_format_check, workflow_check, deps_check, unit])
def check(c: Context):
    """CI-style gate: every check, no changes written. Shell formatting is checked here as well
    as linted — python has always had both `format_check` and a formatter in the gate, and shell
    without the check half meant drift was only ever surfaced by `fix` mutating the file (a
    written script that shfmt disagreed with oscillated in `git status` for weeks, unseen by CI).

    Lock drift (`deps.check`) is gated here for the same reason: CI covered it only by accident,
    through `bootstrap.sh`'s `uv sync --locked`, so a pyproject.toml edit without a re-lock passed
    locally and failed in CI. Every step here stays deterministic and offline — `deps.audit`, whose
    answer moves with the OSV database rather than with the code, is deliberately not in this
    chain."""


@task(pre=[fix, check])
def precommit(c: Context):
    """Fix, then check — the one command to run before considering a change
    done, with no need to know or invoke the individual tools."""


# Explicit namespace, not Collection.from_module's auto-scan: `unit` is imported above for
# `check`'s pre-chain, and the auto-scan adds every Task object it finds in the module — which
# published testing.py's `unit` a second time as `inv quality.unit`. One task, one name.
ns = Collection(
    lint_check,
    lint_apply,
    format_check,
    format_apply,
    type_check,
    shell_check,
    shell_format_check,
    shell_format_apply,
    workflow_check,
    fix,
    check,
    precommit,
)

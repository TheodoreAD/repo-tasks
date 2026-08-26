"""Shared, reproducible quality-tooling invoke tasks. Every command is echoed
(echo=True) so both a human and an agent see exactly what ran — the only
exception is a step that would involve a secret, and none here do.

Running tests is not this module's job — that lives in testing.py, under its own `test` namespace
with one task per tier. `check` pulls in only the unit tier from there, since it is the only tier
with no prerequisites beyond the dev dependency group."""

from pathlib import Path

from invoke import Collection, Context, task

from .configs import require_tool

# Aliased: this module has its own `check`, and the gate needs deps' one in its pre-chain.
from .deps import check as deps_check
from .docs import link_check
from .projects import tracked_files
from .testing import unit, untested_modules


def _sh_files(c: Context):
    return tracked_files(c, "*.sh")


def _workflow_files(c: Context):
    return tracked_files(c, ".github/workflows/*.yml", ".github/workflows/*.yaml")


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
def verify_types(c: Context):
    """Report basedpyright's type-completeness for each package under src/ — how much of the
    published API a consumer sees with a known type.

    A diagnostic, not a gate step, and deliberately does not propagate its exit code:
    `--verifytypes` exits non-zero at anything short of 100%, which every real package is, so
    gating on it would mean either permanent red or a committed baseline number — and a baseline is
    what `contributing/type-checking.md` already rejected for this repo. Run it when working on the
    typed surface; `tests/unit/test_types.py` is what actually pins the signatures that matter.

    No-ops cleanly where there is no src/ layout to inspect."""
    src = Path("src")
    if not src.is_dir():
        print("[quality.verify-types] no src directory — nothing to do")
        return
    require_tool("basedpyright")
    for package in sorted(p for p in src.iterdir() if p.is_dir() and (p / "__init__.py").exists()):
        c.run(f"basedpyright --verifytypes {package.name}", echo=True, warn=True)


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
    """Check every GitHub Actions workflow file (.github/workflows/*.yml): actionlint for
    correctness, zizmor for security. No-ops cleanly on a repo with no workflows, so it is safe in
    every consumer's `check`.

    Two binaries under one task name, the same way `format_check` runs ruff and dprint: the
    developer asks one question ("are my workflows OK?"), and both tools gate on the same file list,
    so the no-op contract is unchanged. They do not overlap — actionlint reads workflow syntax and
    expression correctness, zizmor reads the security properties (credential persistence,
    template injection, permission scope, cache poisoning) that a syntactically perfect workflow
    can still get wrong.

    `--offline` is passed explicitly rather than relied on. zizmor already defaults to offline, but
    it enables its online audits whenever a `GH_TOKEN`/`GITHUB_TOKEN` is visible in the environment
    — which is exactly the case inside CI. A gate step whose rule set depends on whether a token
    happened to be exported is not the deterministic, offline step `check` promises."""
    files = _workflow_files(c)
    if files:
        require_tool("actionlint")
        require_tool("zizmor")
        c.run(f"actionlint {' '.join(files)}", echo=True)
        c.run(f"zizmor --offline {' '.join(files)}", echo=True)


@task(pre=[lint_apply, format_apply, shell_format_apply])
def fix(c: Context):
    """Fix everything auto-fixable: ruff --fix, ruff format, dprint fmt, shfmt -w."""


@task(
    pre=[
        lint_check,
        format_check,
        type_check,
        shell_check,
        shell_format_check,
        workflow_check,
        link_check,
        deps_check,
        untested_modules,
        unit,
    ]
)
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
    verify_types,
    shell_check,
    shell_format_check,
    shell_format_apply,
    workflow_check,
    fix,
    check,
    precommit,
)

"""Shared, reproducible quality-tooling invoke tasks. Every command is echoed (`echo=True`) so both
a human and an agent see exactly what ran — the only exception is a step that would involve a
secret, and none here do.

Under `REPO_TASKS_RUN_REPORT` that echo becomes a one-line report per command, with output folded
on success and replayed on failure, and the two gates end with a verdict line. Nothing in this
module knows about that: `runner.py` owns it, keyed off the `echo=True` these calls already pass,
and `verdict` is a no-op when the mode is off.

Running tests is not this module's job — that lives in testing.py, under its own `test` namespace
with one task per tier. `check` pulls in only the unit tier from there, since it is the only tier
with no prerequisites beyond the dev dependency group."""

from pathlib import Path

from invoke import Collection, Context, task

from .configs import require_tool

# Aliased: this module has its own `check`, and the gate needs deps' one in its pre-chain.
from .deps import check as deps_check

# Aliased for the same reason as deps' check: `build` alone in a gate's pre-chain says nothing
# about what is being built.
from .docs import build as docs_build
from .docs import link_check
from .projects import tracked_files
from .runner import verdict
from .testing import unit, untested_modules


def _sh_files(c: Context):
    return tracked_files(c, "*.sh")


def _workflow_files(c: Context):
    return tracked_files(c, ".github/workflows/*.yml", ".github/workflows/*.yaml")


def _dockerfiles(c: Context):
    """Every Dockerfile in the repo, at any depth. Both spellings the family actually uses: a bare
    `Dockerfile` (the zero-config root image `projects.discover_docker_images` finds) and the
    `<name>.Dockerfile` suffix a repo with several images, or a test fixture, reaches for.

    Three pathspecs rather than one `*Dockerfile`: git's default pathspec matching lets `*` cross
    directory separators, so the one-liner works — and also matches a `my-notes-on-Dockerfile`
    somebody adds later, which would be handed to hadolint as though it were one."""
    return tracked_files(c, "Dockerfile", "*/Dockerfile", "*.Dockerfile")


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


@task(help={"python_version": "Check against this Python instead of pyrightconfig.json's (e.g. 3.13)"})
def type_check(c: Context, python_version: str | None = None):
    """Run basedpyright's type checker.

    The version checked normally comes from pyrightconfig.json, which `configs.pull` derives from
    this project's `requires-python` — one answer an editor's language server and CI both read.
    `--python-version` overrides it for one run, which is the escape hatch for a repo running a
    Python matrix in CI and wanting each entry checked. Verified against basedpyright 1.39.10: the
    flag beats the config file, it does not merely fill in for an absent value.

    Nothing wires this into the shipped workflow, and that is deliberate — static analysis checks
    source against the *declared floor*, and the floor is one value however many interpreters the
    tests run on. A second version only catches a `sys.version_info`-gated branch, which is real but
    too narrow to pay for everywhere. See plans/2026-08-29-python-floor-in-the-shipped-configs.md."""
    require_tool("basedpyright")
    override = f" --pythonversion {python_version}" if python_version else ""
    c.run(f"basedpyright{override}", echo=True)


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


@task
def dockerfile_check(c: Context):
    """Run hadolint against every Dockerfile in the repo. No-ops cleanly on a repo with no images,
    so it is safe in every consumer's `check`.

    hadolint and `docker build --check` are not substitutes, and this repo runs both at different
    tiers. Docker's built-in checks are ~21 rules about build semantics and casing; hadolint is
    ~100 `DL####` rules plus ShellCheck over every `RUN` body — apt pinning, layer merging,
    `--no-install-recommends`, `ADD` vs `COPY`, `latest` base tags, a root user. Only hadolint's
    half is static: `docker build --check` needs a daemon, so it lives in `docker.check` and is
    exercised from the integration tier.

    A finding that does not apply gets `# hadolint ignore=DL####` on the line above it, with the
    reason in a comment beside it — never a flag on this call, and no repo-wide `.hadolint.yaml`
    until an exclusion is genuinely repo-wide. The declining is then visible to whoever next reads
    the Dockerfile, which is where the question comes up."""
    files = _dockerfiles(c)
    if files:
        require_tool("hadolint")
        c.run(f"hadolint {' '.join(files)}", echo=True)


@task(pre=[lint_apply, format_apply, shell_format_apply])
def fix(c: Context):
    """Fix everything auto-fixable: ruff --fix, ruff format, dprint fmt, shfmt -w."""


# The read-only gate, in order. One list so `precommit` can inline it: nesting `check` itself would
# print check's verdict in the middle of a precommit run, with a step count that includes `fix`'s
# steps, and the whole point of the verdict is that it is the last line. A tuple spread into each
# `pre=[...]`: `pre` wants a list of unparameterized tasks, and a shared list literal infers the
# narrower union of these tasks' signatures, which an invariant list cannot widen back.
_CHECKS = (
    lint_check,
    format_check,
    type_check,
    shell_check,
    shell_format_check,
    workflow_check,
    dockerfile_check,
    link_check,
    deps_check,
    untested_modules,
    unit,
)


@task(pre=[*_CHECKS])
def check(c: Context):
    """CI-style gate: every check, no changes written. Shell formatting is checked here as well
    as linted — python has always had both `format_check` and a formatter in the gate, and shell
    without the check half meant drift was only ever surfaced by `fix` mutating the file (a
    written script that shfmt disagreed with oscillated in `git status` for weeks, unseen by CI).

    Lock drift (`deps.check`) is gated here for the same reason: CI covered it only by accident,
    through `bootstrap.sh`'s `uv sync --locked`, so a pyproject.toml edit without a re-lock passed
    locally and failed in CI. Every step here stays deterministic and offline — `deps.audit`, whose
    answer moves with the OSV database rather than with the code, is deliberately not in this
    chain.

    "No changes written" is literal and load-bearing: this half is safe to run concurrently, on a
    read-only checkout, and twice with the same answer. `docs.build` is deliberately **not** here
    for that reason — it writes a built site into the working tree — and lives in `precommit`
    instead. See that task's docstring for the argument it beat.

    The body runs only once every step has passed — invoke stops at the first failing pre-task,
    and the step that failed has already printed the verdict — so all it does is print the PASS,
    and only under `REPO_TASKS_RUN_REPORT`. Stock invoke reaches here and prints nothing."""
    verdict("quality.check")


@task(pre=[fix, *_CHECKS, docs_build])
def precommit(c: Context):
    """Fix, then every step of check, then build the docs site — the one command to run before
    considering a change done, with no need to know or invoke the individual tools.

    `docs.build` is here rather than in `check`, and that placement is the whole decision.
    `zensical build --strict` catches what a renderer objects to and nothing else here sees, but it
    writes a built site into the working tree, and `check` is the read-only CI-style half by
    construction — safe on a concurrent run, on a read-only checkout, and twice with the same
    answer. Building into the tree from a task documented as "no changes written" is a category
    error whatever `.gitignore` thinks of the output, and zensical offers no way to avoid it: its
    `build` takes only `--config-file`, `--clean` and `--strict`, with no output directory at all,
    so the best achievable property is "leaves no net change" rather than "writes nothing".

    The argument this beat, recorded because it is the one that gets re-derived: only `check` runs
    in CI, so putting the build there is the cheapest way to make a docs failure fail the run people
    already watch. The cost is real for a consumer with a docs site and no docs CI job of its own —
    such a repo now needs one, which is what `power-user-linux-setup` did rather than take the
    mutation. A gate half that quietly stopped being read-only would have been the worse trade, for
    every consumer including the majority with no docs site."""
    verdict("quality.precommit")


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
    dockerfile_check,
    fix,
    check,
    precommit,
)

"""Test-running tasks, one per tier. Nested as `test` on the CLI (`inv test.unit`), while the
module keeps the longer name — `test.py` inside an installed package would sit next to CPython's
own stdlib `test` package, and the collection name is set explicitly anyway.

Only `unit` belongs in `quality.check`'s gate: it is the tier with no prerequisites beyond the dev
dependency group, and `contributing/test-tiers.md`'s rule is that the default gate must stay
runnable anywhere. Everything else here needs a Docker daemon.

`unit` deliberately runs a bare `pytest` and names no path. `pytest.ini`'s `testpaths` points at
tests/unit, and pytest's own behaviour when that directory is absent is to warn
("No files were found in testpaths ... Searching recursively from the current directory instead")
and search from the working directory — which is exactly the fallback a simple project with a flat
`tests/` needs, from the tool rather than hand-rolled. Naming the path explicitly would break that:
an explicit path that does not exist is a hard exit-4 usage error, not a warning.
"""

import ast
import re
from pathlib import Path

from invoke import Context, Exit, Result, task

from .configs import require_tool
from .requirements import DOCKER, requires
from .steps import run_step

_INTEGRATION_DIR = Path("tests/integration")

_NO_INTEGRATION = f"no {_INTEGRATION_DIR} directory — nothing to do"

_WORKFLOWS_DIR = Path(".github/workflows")

_NO_WORKFLOWS = f"no {_WORKFLOWS_DIR} directory — nothing to do"

# pytest's "no tests were collected" exit code. Treated as success everywhere here, so a repo with
# no python tests at all (a quality-gates-only repo bootstrapped via configs.ensure-deps, say)
# still passes `check` — the same safe-to-run-unconditionally contract shell_check has.
_NO_TESTS_COLLECTED = 5

# The counts on pytest's closing summary line (`==== 3 failed, 462 passed, 2 warnings in 4.2s ====`).
# Passed, failed and errors only: warnings, skips and the timing are not the verdict.
_PYTEST_COUNT_RE = re.compile(r"\b\d+ (?:passed|failed|errors?)\b")

_SRC_DIR = Path("src")

_UNIT_DIR = Path("tests/unit")

_NO_LAYOUT = f"no {_SRC_DIR} or {_UNIT_DIR} directory — nothing to do"


def _has_code(module: Path) -> bool:
    """Whether a module contains anything a test could exercise — any statement beyond its own
    docstring.

    The case this exists for is a package's `__init__.py`. A generated project's is often exactly
    one line, `\"\"\"<description>\"\"\"`, and demanding a `test_init.py` for it buys a placeholder
    assertion in every repo rather than coverage of anything. Stated generally because it is
    generally true: a module with no code has nothing to test. One with re-exports does — an
    `__all__` or an import someone depends on is a contract, and `repo_tasks/__init__.py`'s own
    collection wiring is exactly that, so this package keeps needing its `test_init.py`.

    A file that does not parse counts as having code: reporting it as "nothing to test" would hide
    it, and it is not this check's job to be the one that finds a syntax error."""
    try:
        tree = ast.parse(module.read_text())
    except SyntaxError:
        return True
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    return bool(body)


def _expected_test_name(stem: str) -> str:
    """The unit-test file a module is expected to have. `__init__.py` maps to `test_init.py`, which
    is what this package and every consumer already call it — `test___init__.py` reads badly and
    nobody writes it."""
    return "test_init.py" if stem == "__init__" else f"test_{stem}.py"


def _pytest_summary(result: Result) -> str | None:
    """What a pytest run reports on its step line and on the gate's verdict: `465 passed`,
    `3 failed, 462 passed`, or `no tests collected`. The one place this package reads a tool's
    output for a number — pytest's summary counts are stable, and they are exactly the line a
    `| tail -3` on the old streaming gate was reaching for."""
    if result.exited == _NO_TESTS_COLLECTED:
        return "no tests collected"
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return None
    counts = [match.group(0) for match in _PYTEST_COUNT_RE.finditer(lines[-1])]
    return ", ".join(counts) or None


def _pytest(c: Context, args: str = "", *, fold: bool = True) -> None:
    """Run pytest, treating "no tests collected" as a pass.

    `fold` is the gate shape: output folded on success, replayed on failure, the count on the step
    line. `coverage` turns it off because its output *is* the report, and the integration tiers
    turn it off because they run for minutes and a human is usually watching them."""
    # `unit` runs inside quality.check, so a dev group behind the repo-tasks-quality manifest
    # reaches this the same way it reaches the tools in quality.py — same preflight, same fix.
    require_tool("pytest")
    command = f"pytest {args}".strip()
    if fold:
        run_step(c, command, ok=frozenset({0, _NO_TESTS_COLLECTED}), note=_pytest_summary)
        return
    result = c.run(command, echo=True, warn=True)
    if not result.ok and result.exited != _NO_TESTS_COLLECTED:
        raise Exit(code=result.exited)


def _integration(c: Context, args: str, label: str) -> None:
    """Run part of the integration tier, or no-op cleanly when the repo has no such tier. The
    existence check is not decoration: unlike `unit`, these targets name a path, and pytest exits
    4 (usage error) on a path that isn't there."""
    if not _INTEGRATION_DIR.exists():
        print(f"[test.{label}] {_NO_INTEGRATION}")
        return
    _pytest(c, f"{_INTEGRATION_DIR} {args}".strip(), fold=False)


@task
def unit(c: Context):
    """Run the unit tier — no Docker, no network, nothing outside tmp_path. The one test task in
    `quality.check`/`precommit`. Falls back to searching from the working directory (with pytest's
    own warning) in a repo whose tests aren't split into tests/unit."""
    _pytest(c)


@task
def untested_modules(c: Context):
    """Check every module in a src-layout package has a tests/unit/test_<module>.py.

    Answers the one question a coverage percentage cannot: which module has no tests at all. This
    tier asserts on mocked command strings, so line coverage would mostly measure how much mocking
    got written — a module with no test file is unambiguous, and contributing/test-tiers.md already
    states the convention this enforces.

    Top-level modules of each package under src/ only: it does not recurse, since a nested package
    is a different unit with its own layout question. A module with no code in it — a docstring-only
    `__init__.py`, typically — is skipped, since the only test it could have is a placeholder. No-ops
    cleanly on a repo with no src/ or no tests/unit — a flat-layout consumer is not doing anything
    wrong."""
    if not _SRC_DIR.is_dir() or not _UNIT_DIR.is_dir():
        print(f"[test.untested-modules] {_NO_LAYOUT}")
        return
    missing = [
        f"{module} has no {_UNIT_DIR / _expected_test_name(module.stem)}"
        for package in sorted(p for p in _SRC_DIR.iterdir() if p.is_dir())
        for module in sorted(package.glob("*.py"))
        if _has_code(module) and not (_UNIT_DIR / _expected_test_name(module.stem)).exists()
    ]
    if not missing:
        return
    for entry in missing:
        print(f"[test.untested-modules] {entry}")
    raise Exit(f"[test.untested-modules] {len(missing)} module(s) with no unit test file", code=1)


@task(help={"html": "Also write a browsable report to htmlcov/ (git-ignored, never committed)"})
def coverage(c: Context, html: bool = False):
    """Report line coverage for the unit tier (pytest --cov, needs pytest-cov from the
    repo-tasks-quality group). A report, never a gate step, and deliberately no `--cov-fail-under`.

    This tier asserts on the command string a task builds against a MockContext, so the number
    largely measures how much mocking got written rather than how much behaviour is covered —
    contributing/test-tiers.md records two real dist.py bugs that survived full unit coverage. A
    threshold on that number is metric-gaming with extra steps. `test.untested-modules` is the half
    with a true answer, and it is the half in `quality.check`.

    Scoped to the packages under src/, so the report is about this project's own code rather than
    about its tests and its dependencies. A repo with no src/ layout falls back to the working
    directory, which is what a flat project wants."""
    packages = (
        sorted(p.name for p in _SRC_DIR.iterdir() if p.is_dir() and (p / "__init__.py").exists())
        if _SRC_DIR.is_dir()
        else []
    )
    args = " ".join(f"--cov={name}" for name in packages) or "--cov=."
    args += " --cov-report=term-missing"
    if html:
        args += " --cov-report=html"
    _pytest(c, args, fold=False)


@requires(DOCKER)
@task
def integration(c: Context):
    """Run the whole integration tier against real local services (Docker, a package index). Needs
    a reachable Docker daemon; no-ops cleanly in a repo with no tests/integration directory."""
    _integration(c, "", "integration")


@requires(DOCKER)
@task
def smoke(c: Context):
    """Run the fast, happy-path slice of the integration tier (`-m smoke`) — enough to know the
    system is wired up at all. No-ops cleanly with no integration tier, and is not an error when
    nothing is marked yet."""
    _integration(c, "-m smoke", "smoke")


@requires(DOCKER)
@task
def regression(c: Context):
    """Run everything in the integration tier that isn't smoke (`-m "not smoke"`) — the broad,
    slower half. No-ops cleanly with no integration tier."""
    _integration(c, '-m "not smoke"', "regression")


@requires(DOCKER)
@task(
    help={
        "job": "Run only this job id (act -j); default: every job the event triggers",
        "event": "GitHub event to simulate (default: push)",
        "dry-run": "Print the plan without running any container (act -n)",
    }
)
def workflows(c: Context, job: str | None = None, event: str = "push", dry_run: bool = False):
    """Run the repo's GitHub Actions workflows locally with act (nektos/act), in Docker containers
    standing in for the hosted runners. Needs a reachable Docker daemon; no-ops cleanly in a repo
    with no .github/workflows directory. Not a tier and not in any gate: it re-runs the gate the
    way CI would, which is only worth doing when a workflow file itself changed."""
    if not _WORKFLOWS_DIR.exists():
        print(f"[test.workflows] {_NO_WORKFLOWS}")
        return
    cmd = f"act {event}"
    if job:
        cmd += f" -j {job}"
    if dry_run:
        cmd += " -n"
    c.run(cmd, echo=True)


@task(pre=[unit, integration])
def all(c: Context):  # noqa: A001 — shadows the builtin, but `inv test.all` is the name that reads right
    """Run every tier: the unit tests, then the whole integration tier."""

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

from pathlib import Path

from invoke import Exit, task

_INTEGRATION_DIR = Path("tests/integration")

_NO_INTEGRATION = f"no {_INTEGRATION_DIR} directory — nothing to do"

# pytest's "no tests were collected" exit code. Treated as success everywhere here, so a repo with
# no python tests at all (a quality-gates-only repo bootstrapped via configs.ensure-deps, say)
# still passes `check` — the same safe-to-run-unconditionally contract shell_check has.
_NO_TESTS_COLLECTED = 5


def _pytest(c, args: str = "") -> None:
    command = f"pytest {args}".strip()
    result = c.run(command, echo=True, warn=True)
    if not result.ok and result.exited != _NO_TESTS_COLLECTED:
        raise Exit(code=result.exited)


def _integration(c, args: str, label: str) -> None:
    """Run part of the integration tier, or no-op cleanly when the repo has no such tier. The
    existence check is not decoration: unlike `unit`, these targets name a path, and pytest exits
    4 (usage error) on a path that isn't there."""
    if not _INTEGRATION_DIR.exists():
        print(f"[test.{label}] {_NO_INTEGRATION}")
        return
    _pytest(c, f"{_INTEGRATION_DIR} {args}".strip())


@task
def unit(c):
    """Run the unit tier — no Docker, no network, nothing outside tmp_path. The one test task in
    `quality.check`/`precommit`. Falls back to searching from the working directory (with pytest's
    own warning) in a repo whose tests aren't split into tests/unit."""
    _pytest(c)


@task
def integration(c):
    """Run the whole integration tier against real local services (Docker, a package index). Needs
    a reachable Docker daemon; no-ops cleanly in a repo with no tests/integration directory."""
    _integration(c, "", "integration")


@task
def smoke(c):
    """Run the fast, happy-path slice of the integration tier (`-m smoke`) — enough to know the
    system is wired up at all. No-ops cleanly with no integration tier, and is not an error when
    nothing is marked yet."""
    _integration(c, "-m smoke", "smoke")


@task
def regression(c):
    """Run everything in the integration tier that isn't smoke (`-m "not smoke"`) — the broad,
    slower half. No-ops cleanly with no integration tier."""
    _integration(c, '-m "not smoke"', "regression")


@task(pre=[unit, integration])
def all(c):  # noqa: A001 — shadows the builtin, but `inv test.all` is the name that reads right
    """Run every tier: the unit tests, then the whole integration tier."""

"""GitHub Actions run status, read through the `gh` CLI.

Exists because push-triggered CI on a repo that is pushed to directly fails quietly: there is no
pull request to turn red, and nobody watches the Actions tab. `status` is what makes the previous
push's result visible before the next one goes out.

Reads only. Nothing here dispatches, re-runs, or cancels a workflow — a task that could re-trigger a
release from a terminal is a different risk profile, and `gh` already does it for the rare case."""

import json
from typing import TypedDict, cast

from invoke import Context, Exit, task

from .configs import require_tool
from .requirements import GH, NETWORK, requires

# A run whose conclusion is one of these is a failure worth stopping for. `cancelled` is not: it is
# usually the concurrency group doing its job when a newer push superseded an older one.
_FAILED = frozenset({"failure", "timed_out", "startup_failure"})

_FIELDS = "status,conclusion,workflowName,headBranch,displayTitle,createdAt,url"


class Run(TypedDict, total=False):
    """One entry of `gh run list --json`. `total=False` because every field is only present if it
    was asked for, and `conclusion` is genuinely absent while a run is still going — a TypedDict per
    shape with one cast at the loader, rather than dict[str, Any] cascading Unknown through every
    caller (contributing/type-checking.md)."""

    status: str
    conclusion: str
    workflowName: str
    headBranch: str
    displayTitle: str
    createdAt: str
    url: str


def _runs(stdout: str) -> list[Run]:
    """`gh run list --json`'s payload, or an empty list when it produced nothing parseable — a repo
    with no runs yet answers `[]`, and a `gh` that failed answers with nothing at all."""
    text = stdout.strip()
    if not text:
        return []
    return cast(list[Run], json.loads(text))


def _describe(run: Run) -> str:
    state = run.get("conclusion") or run.get("status") or "unknown"
    return f"{state:<15} {run.get('workflowName', '?')}  {run.get('createdAt', '?')}  {run.get('url', '')}"


@requires(GH, NETWORK)
@task(
    help={
        "branch": "Branch to report on (default: main)",
        "limit": "How many recent runs to list (default: 10)",
    }
)
def status(c: Context, branch: str = "main", limit: int = 10):
    """Report recent GitHub Actions runs for a branch, and stop if the latest one failed.

    Needs network and an authenticated `gh` — never part of `quality.check`, which stays offline.

    Run it before pushing. The failure it is for is a red run from the *previous* push: CI here is
    push-triggered on a repo with no pull requests, so nothing else surfaces it, and the next push
    otherwise stacks on top of a break nobody has seen. Stopping is keyed to the most recent run
    alone — an older failure that has since been fixed is history, not a reason to block."""
    require_tool("gh")
    result = c.run(f"gh run list --branch {branch} --limit {limit} --json {_FIELDS}", echo=True, warn=True, hide=True)
    if not result.ok:
        raise Exit(f"[ci.status] gh run list failed: {result.stderr.strip()}", code=result.exited)

    runs = _runs(result.stdout)
    if not runs:
        print(f"[ci.status] no runs recorded for {branch}")
        return
    for run in runs:
        print(f"[ci.status] {_describe(run)}")

    latest = runs[0]
    if latest.get("conclusion") in _FAILED:
        raise Exit(
            f"[ci.status] the most recent {branch} run failed — {latest.get('url', '')}",
            code=1,
        )

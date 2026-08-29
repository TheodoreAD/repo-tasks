"""GitHub Actions run status, read through the `gh` CLI.

Exists because push-triggered CI on a repo that is pushed to directly fails quietly: there is no
pull request to turn red, and nobody watches the Actions tab. `status` is what makes the previous
push's result visible before the next one goes out.

Reads only. Nothing here dispatches, re-runs, or cancels a workflow — a task that could re-trigger a
release from a terminal is a different risk profile, and `gh` already does it for the rare case."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from invoke import Context, Exit, task

from .configs import require_tool
from .projects import tracked_files
from .requirements import GH, NETWORK, requires

# A run whose conclusion is one of these is a failure worth stopping for. `cancelled` is not: it is
# usually the concurrency group doing its job when a newer push superseded an older one.
_FAILED = frozenset({"failure", "timed_out", "startup_failure"})

_FIELDS = "databaseId,status,conclusion,workflowName,headBranch,displayTitle,createdAt,url"

# Annotation levels worth printing. `notice` is where GitHub puts routine per-step chatter;
# `warning` is where a deprecation lands, and `failure` accompanies a run that already failed.
_LOUD = frozenset({"warning", "failure"})


class Run(TypedDict, total=False):
    """One entry of `gh run list --json`. `total=False` because every field is only present if it
    was asked for, and `conclusion` is genuinely absent while a run is still going — a TypedDict per
    shape with one cast at the loader, rather than dict[str, Any] cascading Unknown through every
    caller (contributing/type-checking.md)."""

    databaseId: int
    status: str
    conclusion: str
    workflowName: str
    headBranch: str
    displayTitle: str
    createdAt: str
    url: str


class Annotation(TypedDict, total=False):
    """One entry of `gh api .../check-runs/<job-id>/annotations`, same reasoning as `Run`."""

    annotation_level: str
    message: str
    title: str


def _runs(stdout: str) -> list[Run]:
    """`gh run list --json`'s payload, or an empty list when it produced nothing parseable — a repo
    with no runs yet answers `[]`, and a `gh` that failed answers with nothing at all."""
    text = stdout.strip()
    if not text:
        return []
    return cast(list[Run], json.loads(text))


def _job_ids(c: Context, run_id: int) -> list[int]:
    """The job ids of one run. Annotations hang off jobs, not off the run, so there is no way to
    ask for a run's annotations in one call."""
    endpoint = f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}/jobs"
    result = c.run(f"gh api {endpoint} --jq '.jobs[].id'", hide=True, warn=True)
    if not result.ok:
        return []
    return [int(line) for line in result.stdout.split() if line.isdigit()]


def _annotations(c: Context, job_id: int) -> list[Annotation]:
    """One job's annotations, or nothing if the call failed. Never raises: this is the reporting
    half of a task whose real job is the run's conclusion, and a token without the scope to read
    check runs must not turn a working status report into an error."""
    result = c.run(f"gh api repos/{{owner}}/{{repo}}/check-runs/{job_id}/annotations", hide=True, warn=True)
    text = result.stdout.strip() if result.ok else ""
    if not text:
        return []
    return cast(list[Annotation], json.loads(text))


def _report_annotations(c: Context, run: Run):
    """Print the loud annotations on a run's jobs.

    The blind spot this closes: a deprecation notice rides on a run that passes, so every signal
    anyone looks at — the conclusion, the tick in the Actions tab, this task before it — says the
    run is fine. The family's actions sat three majors behind a deprecated Node for roughly eleven
    months behind exactly that signal, found by chance rather than by anything watching.

    Reports only, and deliberately: an annotation is upstream telling you about a deadline, not a
    break, and a task that failed on one would make the pre-push check red for something nobody can
    fix in that moment. See plans/2026-08-28-node20-action-deprecation.md."""
    run_id = run.get("databaseId")
    if not run_id:
        return
    seen: set[str] = set()
    for job_id in _job_ids(c, run_id):
        for annotation in _annotations(c, job_id):
            if annotation.get("annotation_level") not in _LOUD:
                continue
            # The same deprecation is emitted once per job, so a five-job matrix says it five times.
            message = " ".join((annotation.get("message") or "").split())
            if message and message not in seen:
                seen.add(message)
                print(f"[ci.status] {annotation.get('annotation_level')}: {message}")


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
    alone — an older failure that has since been fixed is history, not a reason to block.

    Also prints the latest run's warning and failure annotations, which is where a deprecation
    notice lives — the one signal a green conclusion hides. Those report only; nothing here stops
    on an annotation."""
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
    _report_annotations(c, latest)
    if latest.get("conclusion") in _FAILED:
        raise Exit(
            f"[ci.status] the most recent {branch} run failed — {latest.get('url', '')}",
            code=1,
        )


# `uses:` as a workflow actually writes it: on a step (`- uses:`), on a job (a reusable workflow),
# quoted or not, with an optional trailing `# v1.2.3` comment beside a SHA pin.
_USES = re.compile(r"""^\s*(?:-\s*)?uses:\s*['"]?(?P<ref>[^\s'"#]+)['"]?(?:\s*#\s*(?P<comment>\S+))?""")

_SHA = re.compile(r"^[0-9a-f]{40}$")

# The leading numeric run of a tag, `v` or not: v7, v7.0.1, 0.3, 1.2.3-rc1 -> (1, 2, 3).
_VERSION = re.compile(r"^v?(?P<parts>\d+(?:\.\d+)*)")


@dataclass(frozen=True)
class ActionUse:
    """One `uses:` site, reduced to what a currency check needs."""

    action: str
    """`owner/repo`, with any `/.github/workflows/...` path of a reusable workflow dropped."""

    version: str | None
    """The human-readable version this site pins. The ref itself for `@v7`; the trailing `# v7.0.1`
    comment for a SHA pin, since the SHA says nothing on its own; None when a SHA carries no
    comment, which is its own finding."""

    where: str


def _parts(text: str) -> tuple[int, ...] | None:
    match = _VERSION.match(text)
    return tuple(int(p) for p in match["parts"].split(".")) if match else None


def _is_behind(pinned: str, latest: str) -> bool | None:
    """Whether `pinned` is behind `latest`, compared only at the precision the pin actually states.

    `@v7` against a latest of `v7.0.1` is current, not behind: a bare major is a moving tag that
    already resolves to the newest release under it. `@v9.0.0` against `v10.0.1` is behind. None
    when either side is not a version at all — a branch name, a date tag, a calver scheme this
    cannot rank — because guessing there produces confident nonsense."""
    pin, current = _parts(pinned), _parts(latest)
    if pin is None or current is None:
        return None
    return current[: len(pin)] > pin


def _uses_in(text: str, where: str) -> list[ActionUse]:
    uses: list[ActionUse] = []
    for line in text.splitlines():
        match = _USES.match(line)
        if match is None:
            continue
        ref = match["ref"]
        # A local action or a container image is nobody's release to track.
        if ref.startswith((".", "docker://")) or "@" not in ref:
            continue
        path, _, version = ref.partition("@")
        action = "/".join(path.split("/")[:2])
        if _SHA.match(version):
            comment = match["comment"]
            version = comment if comment and _parts(comment) else ""
        uses.append(ActionUse(action=action, version=version or None, where=where))
    return uses


def _latest_tag(c: Context, action: str) -> str | None:
    """The action's latest release tag, or None when it publishes no releases at all — several
    popular actions tag without releasing, and that is not an error to report as one."""
    result = c.run(f"gh api repos/{action}/releases/latest --jq .tag_name", hide=True, warn=True)
    return result.stdout.strip() if result.ok else None


@requires(GH, NETWORK)
@task(
    help={
        "path": "Directory of workflow files to read (default: .github/workflows)",
    },
    name="check-actions",
)
def check_actions(c: Context, path: str = ".github/workflows"):
    """Report which GitHub Actions used in this repo's workflows are behind their latest release.

    Needs network and an authenticated `gh` — never part of `quality.check`, which stays offline.

    Companion to `status`, covering the half annotations cannot. GitHub annotates what it has
    decided to deprecate; it says nothing about an action merely being behind. Measured on this repo
    2026-08-29: of three actions that were out of date, one was annotated and two were invisible to
    anything but this question.

    Reports only. Nothing here edits a workflow, and that is the design rather than a missing
    feature — the cost of a bump is not the edit, it is reading the major's release notes and
    deciding whether its breaking change reaches this repo. A tool that rewrites the file does the
    cheap half and leaves the risk unread. See plans/2026-08-28-node20-action-deprecation.md.

    `--path` because the highest-value call site in this family is a template's workflows rather
    than a repo's own — a generated repo inherits whatever the template pins."""
    require_tool("gh")
    files = tracked_files(c, f"{path}/*.yml", f"{path}/*.yaml")
    if not files:
        print(f"[ci.check-actions] no workflow files under {path} — nothing to do")
        return

    uses: list[ActionUse] = []
    for name in files:
        uses.extend(_uses_in(Path(name).read_text(), Path(name).name))
    if not uses:
        print("[ci.check-actions] no third-party actions in use — nothing to do")
        return

    latest = {action: _latest_tag(c, action) for action in sorted({u.action for u in uses})}
    behind = 0
    for action, version in sorted({(u.action, u.version) for u in uses}, key=lambda p: (p[0], p[1] or "")):
        where = ", ".join(sorted({u.where for u in uses if u.action == action and u.version == version}))
        newest = latest[action]
        if version is None:
            verdict = "no version comment beside its SHA pin"
        elif newest is None:
            verdict = "publishes no releases — check its tags by hand"
        elif _is_behind(version, newest) is None:
            verdict = f"cannot be ranked against latest {newest}"
        elif _is_behind(version, newest):
            verdict = f"BEHIND — latest {newest}"
            behind += 1
        else:
            verdict = f"current (latest {newest})"
        print(f"[ci.check-actions] {action}@{version or '?'}  {verdict}  [{where}]")

    print(f"[ci.check-actions] {behind} of {len(latest)} action(s) behind")

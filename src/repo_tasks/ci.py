"""GitHub Actions run status, read through the `gh` CLI.

Exists because push-triggered CI on a repo that is pushed to directly fails quietly: there is no
pull request to turn red, and nobody watches the Actions tab. `status` is what makes the previous
push's result visible before the next one goes out.

Reads only. Nothing here dispatches, re-runs, or cancels a workflow — a task that could re-trigger a
release from a terminal is a different risk profile, and `gh` already does it for the rare case."""

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from invoke import Context, Exit, task

from .projects import tracked_files, trunk_branch
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


def _require_gh() -> None:
    """Preflight the `gh` CLI, naming what actually installs it.

    Deliberately not `configs.require_tool`, for the same reason `docs._require_zensical` is not:
    that message names the `repo-tasks-quality` manifest and `dependency-groups.dev`, and tells the
    reader to run `configs.ensure-deps`, `deps.lock` and `venv.sync`. `gh` is in no manifest and is
    not a Python package at all, so a consumer following that remediation syncs a dependency group
    and finds nothing has changed. Every other tool this package preflights does come from the
    manifest, which is what makes `require_tool` right everywhere else and wrong here."""
    if shutil.which("gh") is not None:
        return
    print(
        "[ci] gh not found on PATH — these tasks read the GitHub API through the GitHub CLI, which "
        "is installed with the system package manager (see https://cli.github.com), not from any "
        "Python dependency group."
    )
    print("[ci] next: install gh, then `gh auth login`")
    raise Exit(code=1)


# For every `gh` call whose raw JSON is parsed. gh colours JSON into a pipe when `CLICOLOR_FORCE` is
# set, and `json.loads` cannot read it. `NO_COLOR` does not override that, and neither does piping
# through `--jq .`; an explicit `CLICOLOR_FORCE=0` does. Measured against gh 2.101.0, 2026-09-28.
# `--jq` calls that return a bare scalar come back plain either way and need nothing.
_PLAIN_GH = {"CLICOLOR_FORCE": "0"}


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
    result = c.run(
        f"gh api repos/{{owner}}/{{repo}}/check-runs/{job_id}/annotations", hide=True, warn=True, env=_PLAIN_GH
    )
    text = result.stdout.strip() if result.ok else ""
    if not text:
        return []
    return cast(list[Annotation], json.loads(text))


def _report_annotations(c: Context, run: Run) -> None:
    """Print the loud annotations on a run's jobs.

    The blind spot this closes: a deprecation notice rides on a run that passes, so every signal
    anyone looks at — the conclusion, the tick in the Actions tab, this task before it — says the
    run is fine. The family's actions sat three majors behind a deprecated Node for roughly eleven
    months behind exactly that signal, found by chance rather than by anything watching.

    Reports only, and deliberately: an annotation is upstream telling you about a deadline, not a
    break, and a task that failed on one would make the pre-push check red for something nobody can
    fix in that moment. See contributing/quality-gate.md, "Action currency has two halves"."""
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
        "branch": "Branch to report on (default: this repo's trunk)",
        "limit": "How many recent runs to list (default: 10)",
    }
)
def status(c: Context, branch: str | None = None, limit: int = 10):
    """Report recent GitHub Actions runs for a branch, and stop if the latest one failed.

    Needs network and an authenticated `gh` — never part of `quality.check`, which stays offline.

    Run it before pushing. The failure it is for is a red run from the *previous* push: CI here is
    push-triggered on a repo with no pull requests, so nothing else surfaces it, and the next push
    otherwise stacks on top of a break nobody has seen. Stopping is keyed to the most recent run
    alone — an older failure that has since been fixed is history, not a reason to block.

    Also prints the latest run's warning and failure annotations, which is where a deprecation
    notice lives — the one signal a green conclusion hides. Those report only; nothing here stops
    on an annotation."""
    _require_gh()
    branch = branch or trunk_branch()
    command = f"gh run list --branch {branch} --limit {limit} --json {_FIELDS}"
    result = c.run(command, echo=True, warn=True, hide=True, env=_PLAIN_GH)
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

    sha: str | None = None
    """The commit a SHA pin names, None for a tag or branch ref. Kept because a pin's comment is
    only a claim about it — see `_tag_commit`."""


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
        sha = None
        if _SHA.match(version):
            sha = version
            comment = match["comment"]
            version = comment if comment and _parts(comment) else ""
        uses.append(ActionUse(action=action, version=version or None, where=where, sha=sha))
    return uses


def reusable_pins(text: str, path_suffix: str) -> list[str]:
    """Every ref a `uses:` in this workflow text pins for a reusable workflow whose path ends in
    `path_suffix` — `[]` when it calls none.

    Reuses `_USES` rather than growing a second `uses:` parser, since that grammar has exactly one
    correct reading and `check_actions` already encodes it. What differs is what gets kept: this
    keeps the **path**, because the question is which workflow is being called, where `_uses_in`
    deliberately reduces a ref to `owner/repo` since a currency check only cares whose releases to
    track.

    Added for `consumers.diff`, which asks whether each consumer calls this repo's
    `security-reusable.yml` and at what SHA — an addition to a consumer rather than a `configs.pull`,
    so nothing compares it and a stale pin goes unremarked (see contributing/quality-gate.md)."""
    pins: list[str] = []
    for line in text.splitlines():
        match = _USES.match(line)
        if match is None:
            continue
        path, _, ref = match["ref"].partition("@")
        if path.endswith(path_suffix) and ref:
            pins.append(ref)
    return pins


def _latest_tag(c: Context, action: str) -> str | None:
    """The action's latest release tag, or None when it publishes no releases at all — several
    popular actions tag without releasing, and that is not an error to report as one."""
    result = c.run(f"gh api repos/{action}/releases/latest --jq .tag_name", hide=True, warn=True)
    return result.stdout.strip() if result.ok else None


def _tag_commit(c: Context, action: str, tag: str) -> str | None:
    """The commit `tag` resolves to in `action`'s repo, or None when there is no such tag.

    The commits endpoint rather than `git/ref/tags/<tag>`: for an annotated tag the ref points at a
    tag object, not a commit, so comparing it with a pinned SHA would report a mismatch on every
    honest pin to an annotated release. `commits/<ref>` peels through to the commit, which is what a
    `uses:` SHA names. Measured 2026-09-26 on `pypa/gh-action-pypi-publish` `v1.12.4`, an annotated
    tag: `git/ref` answered the tag object `7f25271a`, `commits/` the commit `76f52bc8`, and
    `git ls-remote` agrees with the second as `v1.12.4^{}`. `actions/checkout` and `setup-uv` tag
    lightweight, so this repo's own pins cannot tell the two endpoints apart."""
    result = c.run(f"gh api repos/{action}/commits/{tag} --jq .sha", hide=True, warn=True)
    return result.stdout.strip() if result.ok and result.stdout.strip() else None


def _report_untrue_pin_comments(c: Context, uses: list[ActionUse]) -> int:
    """Check each SHA pin's version comment against the commit its tag actually names, and report
    the ones that do not match. Returns how many did not.

    Without this, a `# v7.0.1` comment beside a SHA that is something else reads as current — the
    currency verdict trusts the comment, and the comment is the one part of a pin nothing verifies.
    This is the floor `pinact` covers and the check here lacked; one call per distinct pin, the same
    lookup a human makes re-resolving a pin by hand."""
    pins: dict[tuple[str, str, str], set[str]] = {}
    for u in uses:
        if u.sha and u.version:
            pins.setdefault((u.action, u.version, u.sha), set()).add(u.where)
    untrue = 0
    for (action, version, sha), sites in sorted(pins.items()):
        where = ", ".join(sorted(sites))
        actual = _tag_commit(c, action, version)
        if actual == sha:
            continue
        untrue += 1
        found = f"{version} is {actual[:12]}" if actual else f"{version} is not a tag of {action}"
        print(f"[ci.check-actions] {action}@{sha[:12]}  UNTRUE COMMENT — says {version}, but {found}  [{where}]")
    return untrue


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
    cheap half and leaves the risk unread. The survey that priced the alternatives is in
    contributing/quality-gate.md, "Workflow hardening".

    `--path` because the highest-value call site in this family is a template's workflows rather
    than a repo's own — a generated repo inherits whatever the template pins.

    A SHA pin's currency is read from its `# vX.Y.Z` comment, so each such comment is also checked
    against the commit its tag names; an untrue one is reported beside the currency lines. See
    `_report_untrue_pin_comments`."""
    _require_gh()
    files = tracked_files(c, f"{path}/*.yml", f"{path}/*.yaml")
    if not files:
        print(f"[ci.check-actions] no workflow files under {path} — nothing to do")
        return

    uses: list[ActionUse] = []
    for name in files:
        uses.extend(_uses_in(Path(name).read_text(encoding="utf-8"), Path(name).name))
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

    untrue = _report_untrue_pin_comments(c, uses)
    tail = f"; {untrue} SHA pin(s) whose version comment is untrue" if untrue else ""
    print(f"[ci.check-actions] {behind} of {len(latest)} action(s) behind{tail}")

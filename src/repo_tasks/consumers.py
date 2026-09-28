"""What every repo consuming this package is behind on, measured in one command.

The other half of `configs.py`'s subject, seen from the producer. `configs.diff` answers "is the
repo I am standing in behind", which is the question a consumer's own session asks; this answers
"which of them are, and on what", which is the question that goes unasked until something breaks —
`ingesta` and `invoke-stubs` each drifted for weeks with nothing looking at them, and both were
found by hand on 2026-09-13 rather than by anything that runs.

It also reports the two things `configs.diff` cannot, both of which are files at known paths rather
than anything it compares:

- **The pin.** An unpinned `bootstrap-repo-tasks.sh` installs whatever `main` is at CI run time
  however recently that repo's configs were pulled, which is the state that makes a push here a
  deploy. Until 2026-09-26 a consumer swept without the stamp step looked identical to one swept with
  it. A consumer with no bootstrap pins through its own `pyproject.toml` and lock instead, and there
  the declared git ref is the pin.
- **The security-workflow caller.** An *addition* to a consumer rather than a `configs.pull`, so
  nothing compares it — and where it does exist, its SHA pin goes stale in silence.

Both are read by content rather than by looking for an expected filename. That is not fastidiousness:
letting a filename stand in for what it usually contains is how this family's consumer set came to be
miscounted three times in three weeks, and a caller in `audit.yml` is a caller.

Read-only by construction, and that is a contract rather than a description: `diff` is one of the
names this machine's Claude Code allowlist auto-approves, so a task called `diff` that mutated
anything would run unprompted. Nothing here writes into a consumer's tree — no `pull`, no
`ensure-deps`, no lock, and the pin is read rather than corrected. Acting on what it reports stays
manual and stays a session in that repo, because sweeping a consumer means running its tasks in its
tree.

See contributing/consumer-sweep.md, "What counts as a consumer", for why the list of consumers is
declared rather than derived, and the rest of that file for what to do about what this prints.
"""

import contextlib
import re
import tomllib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path
from typing import cast

from invoke import Context, task
from invoke.exceptions import Exit

from .ci import reusable_pins
from .configs import Drift, drift_summary, unreadable_pyproject
from .projects import Consumer, discover_consumers, projects_root
from .selfinstall import read_pin

_SECURITY_REUSABLE = ".github/workflows/security-reusable.yml"
"""This repo's own path for the workflow a consumer calls — matched as a suffix of the `uses:` ref."""

_SHA = re.compile(r"^[0-9a-f]{40}$")

_GIT_REQUIREMENT = re.compile(r"^repo-tasks\s*@\s*git\+(?P<url>\S+)\s*$")
"""A PEP 508 direct reference to this package from git — the form a consumer's own lock resolves."""

_RELEASE_TAG = re.compile(r"^v\d+(\.\d+)*$")


def _measured_version() -> str:
    """What this report was produced by, printed with it.

    Comparability is the point of running one loop instead of visiting each repo: a per-consumer
    answer is only meaningful against a named version of this package, and a hand-run sweep that
    used the global tool in one repo and a working tree in another produces two answers that cannot
    be put in the same table. Naming it costs a line and removes the whole question."""
    try:
        return _installed_version("repo-tasks")
    except PackageNotFoundError:  # a working tree that was never installed, editable or otherwise
        return "unknown"


def _measure(consumer: Consumer, source: str | None) -> Drift | str:
    """One consumer's drift, read from inside its tree — or, where its pyproject.toml does not
    parse, the sentence saying so, so that one broken consumer is a line in the report rather than a
    traceback ending the loop before the others are measured.

    `chdir` rather than threading a root through `configs.py`, deliberately. Every helper there
    already reads the tree it is standing in, and this task is the only caller that ever wants a
    different one — parameterising them to serve one caller would put the cost on every future
    reader of the module that does the real work. `contextlib.chdir` restores on the way out
    including on an exception, and this loop is sequential, which is the condition it needs."""
    with contextlib.chdir(consumer.path):
        if (problem := unreadable_pyproject()) is not None:
            return problem
        return drift_summary(source)


@dataclass(frozen=True)
class _Finding:
    """One clause of a consumer's report line, and whether it means that consumer is behind.

    Most findings do, and `behind=True` is the default for that reason. The exception is a consumer
    with **no CI at all**: that is an open question about the repo rather than drift from this one —
    `invoke-stubs` has no `.github/` directory, and the plan records that the security-caller item
    cannot be done there until somebody decides whether that repo has CI. Reporting it as behind
    would be asserting the answer, and staying silent would lose the one place where a green local
    gate is the whole of the evidence. So it is said and not counted."""

    text: str
    behind: bool = True


def _security_finding(consumer: Consumer, head: str | None) -> _Finding | None:
    """Whether this consumer calls the shipped reusable security workflow, and at what commit.

    The last mechanical item on the complement list. It is an **addition** to a consumer rather than
    a `configs.pull`, so no config comparison can see it — the file does not exist in four of the six
    repos, and where it does exist nothing checks that the SHA it pins is still the current one.

    `head` is the newest commit touching `security-reusable.yml` in this repo, read once by the
    caller. None where that read failed (a shallow clone, or not a git checkout), in which case the
    presence half still answers and the currency half is skipped rather than guessed."""
    workflows = consumer.path / ".github" / "workflows"
    if not workflows.is_dir():
        return _Finding("no CI at all, so nothing calls the security workflow", behind=False)

    pins = [
        pin
        for path in sorted(workflows.iterdir())
        if path.is_file()
        for pin in reusable_pins(path.read_text(encoding="utf-8", errors="replace"), _SECURITY_REUSABLE)
    ]
    if not pins:
        return _Finding(f"no caller for {_SECURITY_REUSABLE}")
    # Read by content across every workflow rather than by looking for `security.yml`: this plan's
    # own recurring mistake is letting a filename stand in for the thing it usually contains.
    if head is not None:
        stale = next((pin for pin in pins if _SHA.match(pin) and pin != head), None)
        if stale is not None:
            return _Finding(f"security caller pinned to {stale[:7]}, the reusable workflow is at {head[:7]}")
    loose = next((pin for pin in pins if not _SHA.match(pin)), None)
    if loose is not None:
        return _Finding(f"security caller pinned to {loose!r}, not a 40-character SHA")
    return None


def _pin_line(consumer: Consumer, measured: str) -> str | None:
    """What to say about this consumer's bootstrap pin, or None when there is nothing to say.

    The complement item that stayed unreported longest, and the cheapest of the six: the pin is one
    regex over a file at a known path, needing no chdir and no judgement. It is also the one thing
    here that `configs.diff` structurally cannot reach — it compares shipped config files and the dev
    group, and the pin is in neither, so until 2026-09-26 a consumer swept without the stamp step
    looked identical to one swept with it.

    Deliberately compared against the **measured** version rather than the newest upstream tag. The
    newest tag needs the network, which this reporter does not take, and the measured version is the
    better question anyway: it is the one every other line in the same run was produced by, so a
    consumer pinned to something else is behind *this report*, which is what a sweep acts on."""
    pin = read_pin(consumer.path)
    if not pin.present:
        return None  # pins through its own lock, which `_lock_pin_line` reads instead
    if pin.version is None:
        return "bootstrap unpinned — its CI installs whatever `main` is at run time"
    if pin.version != measured:
        return f"bootstrap pinned to v{pin.version}, behind the v{measured} this was measured with"
    return None


def _table(value: object) -> dict[str, object]:
    """A TOML table, or an empty one where the key is absent or holds something else."""
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _items(value: object) -> list[object]:
    """A TOML array, or an empty one where the key is absent or holds something else."""
    return cast(list[object], value) if isinstance(value, list) else []


def _git_refs(pyproject: dict[str, object]) -> list[str | None]:
    """The ref of every git-sourced `repo-tasks` declaration in one parsed pyproject.toml — None for
    a declaration naming no ref at all — and an empty list where nothing declares it from git.

    Two spellings, because both are in the family: a `[tool.uv.sources]` table
    (`power-user-linux-setup`) and a PEP 508 direct reference in a dependency list or group
    (`invoke-stubs`). A PEP 508 ref is whatever follows an `@` in the URL's last path segment, which
    keeps the `git@` of an ssh URL out of it."""
    refs: list[str | None] = []
    source = _table(_table(_table(pyproject.get("tool")).get("uv")).get("sources")).get("repo-tasks")
    for entry in _items(source) or [source]:  # one table, or a list of them split by marker
        table = _table(entry)
        if "git" in table:
            ref = table.get("tag") or table.get("rev") or table.get("branch")
            refs.append(ref if isinstance(ref, str) else None)

    project = _table(pyproject.get("project"))
    lists = [
        project.get("dependencies"),
        *_table(project.get("optional-dependencies")).values(),
        *_table(pyproject.get("dependency-groups")).values(),
    ]
    for requirement in (r for deps in lists for r in _items(deps) if isinstance(r, str)):
        if (match := _GIT_REQUIREMENT.match(requirement)) is not None:
            last_segment = match["url"].split("#", 1)[0].rsplit("/", 1)[-1]
            refs.append(last_segment.rsplit("@", 1)[1] if "@" in last_segment else None)
    return refs


def _lock_pin_line(consumer: Consumer, measured: str) -> str | None:
    """What to say about a `repo-tasks` this consumer declares from git itself, or None when it
    declares none or pins it to the measured release.

    The other half of `_pin_line`. A consumer with no bootstrap pins through its own lock, and until
    2026-09-28 this file took that as "nothing to report" — the re-lock in the sweep was assumed to
    be its equivalent of `stamp`. It was not: both such consumers declared a bare git URL, so every
    re-lock resolved `main`, and they silently kept the behaviour the pinning decision removed
    everywhere else. The declared tag, not the lock, is what a re-lock moves within, so the tag is
    what gets read. An unreadable pyproject.toml says nothing here: `_measure` already reports it."""
    try:
        pyproject = tomllib.loads((consumer.path / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    for ref in _git_refs(pyproject):
        if ref is None:
            return "repo-tasks declared from git with no tag — its lock re-resolves `main`"
        if not _RELEASE_TAG.match(ref):
            return f"repo-tasks declared at {ref!r}, not a release tag"
        if ref.removeprefix("v") != measured:
            return f"repo-tasks declared at {ref}, behind the v{measured} this was measured with"
    return None


def _security_head(c: Context) -> str | None:
    """The newest commit touching this repo's `security-reusable.yml`, so a consumer's pin can be
    compared against something real.

    A local `git log`, not the GitHub API: the reporter takes no network, and the answer is in this
    checkout. `warn=True` because a caller outside a git checkout is a reason to skip the currency
    half, never to fail the whole report."""
    result = c.run(f"git log -1 --format=%H -- {_SECURITY_REUSABLE}", hide=True, warn=True)
    head = result.stdout.strip() if result.ok else ""
    return head if _SHA.match(head) else None


def _report(consumer: Consumer, source: str | None, measured: str, security_head: str | None) -> bool:
    """One consumer's line, and whether it is behind. Prints the absent case rather than skipping
    it: a declared name with no checkout is the failure mode the declared list exists to make
    visible, and a reporter that quietly passed over it would be back to reporting success for a
    consumer it never looked at."""
    if consumer.missing:
        print(f"[consumers.diff] {consumer.name}: NOT FOUND at {consumer.path}")
        return True

    drift = _measure(consumer, source)
    if isinstance(drift, str):
        print(f"[consumers.diff] {consumer.name}: {drift}")
        return True
    pins = [line for line in (_pin_line(consumer, measured), _lock_pin_line(consumer, measured)) if line]
    security = _security_finding(consumer, security_head)
    findings = [*(_Finding(line) for line in pins), *([security] if security else [])]
    if drift.clean and not findings:
        print(f"[consumers.diff] {consumer.name}: up to date")
        return False

    parts: list[str] = []
    if drift.config_files:
        parts.append(f"config files behind: {', '.join(drift.config_files)}")
    if drift.missing_deps:
        parts.append(f"dev group missing: {', '.join(drift.missing_deps)}")
    if drift.unconstrained_deps:
        parts.append(f"declared without the manifest's constraint: {', '.join(drift.unconstrained_deps)}")
    parts.extend(finding.text for finding in findings)
    print(f"[consumers.diff] {consumer.name}: {'; '.join(parts)}")
    if drift.skipped_self is not None:
        print(f"[consumers.diff]   (skipped an entry naming {consumer.name} itself — it is that package)")
    # A finding carrying `behind=False` is said without being counted — see `_Finding`. So a consumer
    # whose only line is "no CI at all" is reported and still exits clean, and one that is also
    # drifted exits 1 on the drift rather than on the open question.
    return not drift.clean or any(finding.behind for finding in findings)


@task(
    help={
        "source": "Where the canonical configs come from, as `configs.diff` takes it — the packaged copies by default.",
        "name": "Measure only the consumer with this name, instead of every declared one.",
    }
)
def diff(c: Context, source: str | None = None, name: str | None = None):
    """Report what every repo declared as a consumer of this package is behind on — drifted config
    files, dev-group entries the manifest has grown, constraints it declares without, an unpinned or
    stale `bootstrap-repo-tasks.sh` or git-declared `repo-tasks`, and a missing or stale caller for
    the shipped reusable security
    workflow — without writing anything anywhere. Exits nonzero if any of them is behind or any
    declared checkout is absent.

    A consumer with no CI at all is reported without counting as behind: whether that repo should have
    workflows is an open question about it, not drift from here.

    The consumers are `repo-tasks.toml`'s `[[consumer]]` entries, resolved under
    `$REPO_TASKS_PROJECTS_ROOT` or this repo's parent directory. Acting on the result is manual and
    belongs in that repo's own session — see contributing/consumer-sweep.md."""
    consumers = discover_consumers()
    if name is not None:
        consumers = [consumer for consumer in consumers if consumer.name == name]
        if not consumers:
            raise Exit(f"[consumers.diff] no [[consumer]] entry named {name!r} in repo-tasks.toml")
    if not consumers:
        print("[consumers.diff] no [[consumer]] entries in repo-tasks.toml — nothing to measure")
        return

    measured = _measured_version()
    security_head = _security_head(c)
    print(f"[consumers.diff] measured with repo-tasks {measured} from {Path(__file__).parent}")
    print(f"[consumers.diff] under {projects_root()}")
    behind = [consumer.name for consumer in consumers if _report(consumer, source, measured, security_head)]
    if behind:
        raise Exit(code=1)

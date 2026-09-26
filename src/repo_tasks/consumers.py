"""What every repo consuming this package is behind on, measured in one command.

The other half of `configs.py`'s subject, seen from the producer. `configs.diff` answers "is the
repo I am standing in behind", which is the question a consumer's own session asks; this answers
"which of them are, and on what", which is the question that goes unasked until something breaks —
`ingesta` and `invoke-stubs` each drifted for weeks with nothing looking at them, and both were
found by hand on 2026-09-13 rather than by anything that runs.

It reports one thing `configs.diff` cannot: **the bootstrap pin.** That command compares shipped
config files and the dev group, and the pin is in neither — it is in a shell script at a known path —
so a consumer swept without the stamp step looked identical to one swept with it until 2026-09-26.
Which is the state that made a push here a deploy: an unpinned `bootstrap-repo-tasks.sh` installs
whatever `main` is at CI run time, however recently that repo's configs were pulled.

Read-only by construction, and that is a contract rather than a description: `diff` is one of the
names this machine's Claude Code allowlist auto-approves, so a task called `diff` that mutated
anything would run unprompted. Nothing here writes into a consumer's tree — no `pull`, no
`ensure-deps`, no lock, and the pin is read rather than corrected. Acting on what it reports stays
manual and stays a session in that repo, because sweeping a consumer means running its tasks in its
tree.

See plans/2026-08-25-consumer-transitions.md for why the list of consumers is declared rather than
derived, and contributing/consumer-sweep.md for what to do about what this prints.
"""

import contextlib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _installed_version
from pathlib import Path

from invoke import Context, task
from invoke.exceptions import Exit

from .configs import Drift, drift_summary
from .projects import Consumer, discover_consumers, projects_root
from .selfinstall import read_pin


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


def _measure(consumer: Consumer, source: str | None) -> Drift:
    """One consumer's drift, read from inside its tree.

    `chdir` rather than threading a root through `configs.py`, deliberately. Every helper there
    already reads the tree it is standing in, and this task is the only caller that ever wants a
    different one — parameterising them to serve one caller would put the cost on every future
    reader of the module that does the real work. `contextlib.chdir` restores on the way out
    including on an exception, and this loop is sequential, which is the condition it needs."""
    with contextlib.chdir(consumer.path):
        return drift_summary(source)


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
        return None  # pins through its own lock; `deps.lock --package repo-tasks` is its equivalent
    if pin.version is None:
        return "bootstrap unpinned — its CI installs whatever `main` is at run time"
    if pin.version != measured:
        return f"bootstrap pinned to v{pin.version}, behind the v{measured} this was measured with"
    return None


def _report(consumer: Consumer, source: str | None, measured: str) -> bool:
    """One consumer's line, and whether it is behind. Prints the absent case rather than skipping
    it: a declared name with no checkout is the failure mode the declared list exists to make
    visible, and a reporter that quietly passed over it would be back to reporting success for a
    consumer it never looked at."""
    if consumer.missing:
        print(f"[consumers.diff] {consumer.name}: NOT FOUND at {consumer.path}")
        return True

    drift = _measure(consumer, source)
    pin = _pin_line(consumer, measured)
    if drift.clean and pin is None:
        print(f"[consumers.diff] {consumer.name}: up to date")
        return False

    parts: list[str] = []
    if drift.config_files:
        parts.append(f"config files behind: {', '.join(drift.config_files)}")
    if drift.missing_deps:
        parts.append(f"dev group missing: {', '.join(drift.missing_deps)}")
    if drift.unconstrained_deps:
        parts.append(f"declared without the manifest's constraint: {', '.join(drift.unconstrained_deps)}")
    if pin is not None:
        parts.append(pin)
    print(f"[consumers.diff] {consumer.name}: {'; '.join(parts)}")
    if drift.skipped_self is not None:
        print(f"[consumers.diff]   (skipped an entry naming {consumer.name} itself — it is that package)")
    return True


@task(
    help={
        "source": "Where the canonical configs come from, as `configs.diff` takes it — the packaged copies by default.",
        "name": "Measure only the consumer with this name, instead of every declared one.",
    }
)
def diff(c: Context, source: str | None = None, name: str | None = None):
    """Report what every repo declared as a consumer of this package is behind on — drifted config
    files, dev-group entries the manifest has grown, constraints it declares without, and an
    unpinned or stale `bootstrap-repo-tasks.sh` — without writing anything anywhere. Exits nonzero if
    any of them is behind or any declared checkout is absent.

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
    print(f"[consumers.diff] measured with repo-tasks {measured} from {Path(__file__).parent}")
    print(f"[consumers.diff] under {projects_root()}")
    behind = [consumer.name for consumer in consumers if _report(consumer, source, measured)]
    if behind:
        raise Exit(code=1)

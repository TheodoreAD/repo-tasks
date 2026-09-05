"""Report mode: one delimited line per effectful command, output folded on success, replayed whole
on failure. Off unless `REPO_TASKS_RUN_REPORT` is set, and when it is off this module is not
imported into invoke's config at all — `inv` behaves exactly as its own documentation says.

    ruff check . | ok | 0.0s | All checks passed!
    ruff format . | ok | 0.0s | 1 file reformatted
    basedpyright | ok | 2.5s | 0 errors, 0 warnings, 0 notes
    pytest | ok | 1.4s | 592 passed in 1.30s
    quality.check | PASS | 15 steps | 4.4s

and on a failure, the command's output replayed whole between its line and the verdict:

    basedpyright | FAIL | exit=1 | 3.1s
    <everything basedpyright printed>
    FAIL | basedpyright | exit=1 (output above)

`contributing/quality-gate.md` carries the decisions; the short version of each is here because
this file is where someone lands when the output surprises them.

**Why an env var and not a default.** The behaviour is a departure from invoke's, so it is opt-in:
a human at a terminal and a CI log both get stock invoke. The population it is for — agent sessions
— has the variable set for it by `power-user-linux-setup`'s `CLAUDECODE`-guarded zshenv snippet,
beside the `PIPE_FAIL` it already sets there for the same reason, so nothing has to be typed by the
session that would never think to type it.

**Why a Runner subclass and not a wrapper at each call site.** `Context.run` builds its runner from
`config.runners.local` (invoke's own extension point — the stock config holds `Local` there), so
swapping the class reaches all ~90 `c.run` calls in this package with no call-site changes and no
monkeypatching. The previous design wrapped eleven of them by hand and left the rest streaming,
which is where the two-output-shapes problem came from.

**What gets a line: exactly the commands that pass `echo=True`.** That is already this package's
marker for "a command with an effect the caller should see" (see
contributing/task-module-conventions.md), while internal queries pass `hide=True` and are silent.
So the report line replaces the echo line, one rule covers every call site, and a new task gets
reporting by following the convention it would follow anyway.

**How a call site opts out: by mentioning `hide` itself.** Invoke rejects unknown `run` kwargs
outright (`_unify_kwargs_with_config` raises `TypeError`), so an extra option would break the very
stock-invoke behaviour this mode exists to preserve. Instead, a caller that passes `hide` at all
has said what it wants and is left alone — `hide=False` on `test.coverage` keeps its report
visible. That is invoke's own interface and a semantic no-op when report mode is off.
"""

import os
import sys
import time
from dataclasses import dataclass, field

from invoke import Exit, Result
from invoke.runners import Local

_ENV_VAR = "REPO_TASKS_RUN_REPORT"

# Longest command echoed before the line is elided in the middle. Long enough for every routine
# gate command; the file-listing steps (actionlint over every workflow) are the ones that overrun.
_MAX_COMMAND = 90


def enabled() -> bool:
    """Whether report mode is on. Read at import by `__init__.py` and again per run, so a test can
    toggle it with `monkeypatch.setenv` without rebuilding the collection."""
    return bool(os.environ.get(_ENV_VAR))


@dataclass
class _Ledger:
    """What the run has reported so far, for the verdict. One per process: invoke runs a gate and
    its whole pre-chain in one interpreter, so module state is the run's state."""

    steps: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


_ledger = _Ledger()


def reset() -> None:
    """Forget every command reported so far. For tests, which run many in one process."""
    global _ledger  # noqa: PLW0603 — the ledger is the run's state, and a test is a run
    _ledger = _Ledger()


def _elide(command: str) -> str:
    """Shorten a command that would otherwise wrap, keeping both ends — the tool at the front and
    the last argument at the back are what identify it."""
    if len(command) <= _MAX_COMMAND:
        return command
    keep = (_MAX_COMMAND - 3) // 2
    return f"{command[:keep]}...{command[-keep:]}"


def summary(result: Result) -> str | None:
    """The last non-empty line the command printed, which for every tool in this gate is its own
    summary — `All checks passed!`, `1 file reformatted`, `592 passed in 1.30s`.

    Measured across the gate 2026-09-05: five of nine commands print exactly one line and it is
    this; three print nothing at all on success; only pytest prints more, and the other nine tenths
    of that is progress noise. So carrying it costs one line and loses nothing worth reading, which
    is what makes folding the rest honest rather than lossy.

    Deliberately generic. Parsing any particular tool's format would be a thing to maintain per
    tool and to break when one changes its wording."""
    for text in (result.stdout, result.stderr):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            # Strip a banner tool's rule characters: pytest's summary arrives as
            # `==== 592 passed in 1.30s ====`, and the padding is decoration, not content.
            return _elide(lines[-1].strip("=- ")) or None
    return None


def _replay(result: Result) -> None:
    """Print a failed command's captured output, stdout then stderr, each to its own stream.

    Flushed at every hand-off: under `2>&1 | tail` a block-buffered stdout and an unbuffered stderr
    would otherwise arrive out of order, and the verdict has to be the last line."""
    for text, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        if not text:
            continue
        stream.write(text if text.endswith("\n") else text + "\n")
        stream.flush()


class ReportingLocal(Local):
    """`Local`, plus a report line for every command run with `echo=True`.

    Anything else — an internal `hide=True` query, or a caller that named `hide` itself — is passed
    to `Local` untouched, so this class changes nothing about how those commands behave."""

    # No `@typing.override`: it lands in 3.12 and this package's floor is 3.11 (pyrightconfig.json,
    # pyproject's requires-python), so the decorator would not import on the oldest interpreter the
    # gate type-checks against.
    def run(self, command: str, **kwargs: object) -> Result:  # pyright: ignore[reportImplicitOverride]
        # Raw kwargs, before invoke folds them into config defaults: membership is the signal, and
        # `hide=False` has to stay distinguishable from an absent `hide`.
        if not kwargs.get("echo") or "hide" in kwargs:
            return super().run(command, **kwargs)
        return self._reported(command, **kwargs)

    def _reported(self, command: str, **kwargs: object) -> Result:
        # The caller owns the exit code when it passed `warn`; without it, invoke's contract is to
        # raise, and this mode raises `Exit` instead so the tool's own output stays the last thing
        # before the verdict. `UnexpectedExit` would append its own 10-line excerpt after the full
        # replay.
        caller_warns = bool(kwargs.get("warn"))
        label = _elide(command)
        # Half a line before the run, so a killed or hung command names itself — the failure mode
        # that cost this package five days on `docker login`.
        print(f"{label} | ", end="", flush=True)
        started = time.perf_counter()
        result = super().run(command, **{**kwargs, "echo": False, "hide": True, "warn": True})
        seconds = time.perf_counter() - started
        parts = [*_status(result, caller_warns), f"{seconds:.1f}s"]
        note = summary(result)
        if note:
            parts.append(note)
        print(" | ".join(parts), flush=True)
        _ledger.steps += 1
        _ledger.seconds += seconds
        if result.ok:
            return result
        # Replay before deciding what to do about it. A `warn=True` caller is about to read this
        # output itself — `deps.lock` scrapes stderr for uv's moved-member hint — and folding it
        # away would leave the caller's own message with nothing above it explaining the failure.
        _replay(result)
        if caller_warns:
            return result
        print(f"FAIL | {label} | exit={result.exited} (output above)", flush=True)
        raise Exit(code=result.exited)


def _status(result: Result, caller_warns: bool) -> list[str]:
    """The status tokens for a command's line.

    A `warn=True` caller is about to decide for itself whether a non-zero exit is a failure, so the
    line reports the code and does not call it one — pytest's exit 5 ("no tests collected") is a
    pass in a repo with no tests yet, and `FAIL` there would describe something that never
    happened."""
    if result.ok:
        return ["ok"]
    if caller_warns:
        return [f"exit={result.exited}"]
    return ["FAIL", f"exit={result.exited}"]


def verdict(gate: str) -> None:
    """Print a gate's PASS line: how many commands ran and how long they took, as the last line of
    the run.

    Gated on the ledger rather than on the environment, so there is one switch and not two: only
    `ReportingLocal` ever adds to it, so nothing was reported means report mode is off and a gate
    body stays silent under stock invoke. Reading the env var here instead would let the two
    disagree — the runner is chosen once at import, while `os.environ` can move afterwards.

    Only ever a PASS — a failing command has already printed its own FAIL verdict and raised, and
    invoke never reaches a gate's body when a task in its pre-chain fails."""
    if not _ledger.steps:
        return
    steps = f"{_ledger.steps} step{'' if _ledger.steps == 1 else 's'}"
    print(f"{gate} | PASS | {steps} | {_ledger.seconds:.1f}s", flush=True)

"""A gate step's output shape: one line per command, folded on success, replayed in full on failure,
and a verdict as the last line of the run.

Every gate step — the `quality.*` checks and fixes, `test.unit`, `deps.check`, `docs.build` — runs
through `run_step` rather than a bare `c.run(..., echo=True)`, and the gates end with `verdict`.
What that buys, measured across every consumer of this package over the week to 2026-09-05: 58% of
gate runs were piped through `head`/`tail`, almost all of them asking for the last few lines of a
~50-line success, which is where the pytest summary was. The line a reader wants is the verdict,
so the verdict is the last line and everything else is one line per step:

    ruff check . ............................................. ok  0.4s
    basedpyright ............................................. ok  3.1s
    pytest ................................................... ok  4.5s  465 passed
    quality.check: PASS  11 steps, 465 passed, 8.0s

and on a failure, the step's captured output replayed whole between its line and the verdict:

    basedpyright ............................................. FAIL  exit 1
    <everything basedpyright printed>
    FAIL  basedpyright exited 1 (output above)

The command line is still printed for every step, so what ran stays visible and copy-pasteable
(see contributing/task-module-conventions.md, "Echo every command that does something"); only a
successful step's output is folded. The verdict names the failing command, so a `| tail -3` on a
red run shows the failure rather than invoke's generic "bad command exit code" wrapped around
whatever the tool printed last — and that stays true on a machine without pipefail in its shell.

Quiet is the default and streaming is opt-in: `quality.verbose` in invoke's config, which the root
`ns` declares so it is settable as `INVOKE_QUALITY_VERBOSE=1` or in an `invoke.yaml`. Opt-in quiet
would have left the piping where it was — the session that pipes is the one that never reaches for
a flag. It is config rather than a `--verbose` on the gate tasks because invoke runs a task's
`pre=[...]` chain before its body, so a flag on `check` could not reach the steps it governs.

The counts on the verdict line are what each step reported in its note: pytest's `N passed` is the
one number anyone was tailing for, and nothing else parses tool output — every other step reports
ok or FAIL and its wall time. See contributing/quality-gate.md, "What the gate prints"."""

import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from invoke import Context, Exit, Result

# Column the status starts at. Long enough for every routine gate command (the longest,
# `dprint check --config-discovery=ignore-descendants`, is 50 characters); a file-listing step that
# overruns it still gets three dots and the same status, only further right.
_STATUS_COLUMN = 56

_OK = frozenset({0})

# A step's verdict: what it reports about its own output, for its line and for the gate's.
Note = Callable[[Result], str | None]


@dataclass
class _Ledger:
    """What the run has done so far, for the verdict. One per process: invoke runs a gate and its
    whole pre-chain in one interpreter, so module state is the run's state."""

    steps: int = 0
    seconds: float = 0.0
    notes: list[str] = field(default_factory=list)


_ledger = _Ledger()


def reset() -> None:
    """Forget every step run so far. For tests, which run many steps in one process."""
    global _ledger  # noqa: PLW0603 — the ledger is the run's state, and a test is a run
    _ledger = _Ledger()


def verbose(c: Context) -> bool:
    """Whether steps stream their output instead of folding it — `quality.verbose` in invoke's
    config, absent (a hand-built Collection, a MockContext) meaning quiet."""
    # invoke's Config is a nested mapping in all but name — DataProxy forwards `get` to the dict it
    # wraps — and the stub does not type its lookups, so the read goes through the mapping shape.
    config = cast("Mapping[str, Mapping[str, object]]", cast(object, c.config))
    return bool(config.get("quality", {}).get("verbose", False))


def run_step(c: Context, command: str, *, ok: frozenset[int] = _OK, note: Note | None = None) -> Result:
    """Run one gate command and print its line: the command, dots, and `ok` with its wall time or
    `FAIL` with its exit code.

    On success the output is folded away (or streamed, under `quality.verbose`) and the result is
    returned. On failure the captured output is replayed whole, the verdict names the command, and
    the task exits with the command's own code — the same code a bare `c.run` would have raised
    through `UnexpectedExit`, without invoke's wrapper text pushing the tool's last line up.

    `ok` is the exit codes that count as success — pytest's 5 ("no tests collected") is a pass for
    a repo with no tests yet. `note` turns the result into a short summary for the line and for the
    verdict; pytest's `465 passed` is the one this exists for."""
    stream = verbose(c)
    dots = "." * max(3, _STATUS_COLUMN - len(command) - 1)
    label = f"{command} {dots} "
    if not stream:
        # Half a line before the run, so a human sees what is running and a killed run shows
        # where it was; the status completes it.
        print(label, end="", flush=True)
    started = time.perf_counter()
    result = c.run(command, echo=True, warn=True) if stream else c.run(command, hide=True, warn=True)
    seconds = time.perf_counter() - started
    passed = result.exited in ok
    summary = note(result) if note is not None else None
    status = f"ok  {seconds:.1f}s" if passed else f"FAIL  exit {result.exited}"
    if summary:
        status += f"  {summary}"
    print(f"{label}{status}" if stream else status, flush=True)
    if passed:
        _ledger.steps += 1
        _ledger.seconds += seconds
        if summary:
            _ledger.notes.append(summary)
        return result
    if not stream:
        _replay(result)
    print(f"FAIL  {command} exited {result.exited} (output above)", flush=True)
    raise Exit(code=result.exited)


def _replay(result: Result) -> None:
    """Print a failed step's captured output, stdout then stderr, each to its own stream.

    Flushed at every hand-off: under `2>&1 | tail` a block-buffered stdout and an unbuffered stderr
    would otherwise arrive out of order, and the verdict has to be the last line."""
    for text, stream in ((result.stdout, sys.stdout), (result.stderr, sys.stderr)):
        if not text:
            continue
        stream.write(text if text.endswith("\n") else text + "\n")
        stream.flush()


def verdict(gate: str) -> None:
    """Print a gate's PASS line: how many steps ran, what they reported, and their total time.

    Only ever a PASS — a failing step has already printed its own FAIL verdict and exited, since
    invoke never reaches a gate's body when a task in its pre-chain fails."""
    steps = f"{_ledger.steps} step{'' if _ledger.steps == 1 else 's'}"
    print(f"{gate}: PASS  {', '.join([steps, *_ledger.notes, f'{_ledger.seconds:.1f}s'])}", flush=True)

---
status: idea
updated: 2026-09-05
---

# Run reporting as an opt-in agent mode, not as invoke's new default

## Context

`plans/`-less background: the gate-folding change landed and was pushed on 2026-09-05 (`ba9e8e6`,
`f532707`). It replaced eleven `c.run(cmd, echo=True)` gate steps with `steps.run_step`, which
captures output, prints one dotted status line per step, replays on failure and ends the gate with a
verdict. Folding is the default; `INVOKE_QUALITY_VERBOSE=1` restores streaming.

The user's objection is the rule of least surprise, and it holds. Three specific violations:

1. **The default changed for everyone.** A human at the terminal running `inv quality.check` now
   gets a folded report instead of tool output, having asked for nothing. `ruff format .`
   reformatting three files reports `ok`.
2. **Only eleven of roughly ninety `c.run` call sites changed**, so the package now has two output
   shapes. `inv deps.check` reports a step line; `inv deps.lock` streams. `gitflow.py` alone holds
   41 `c.run` calls, none of them touched.
3. **The exception contract changed.** A failing gate step raises `Exit(code)` where invoke would
   have raised `UnexpectedExit`.

And the switch is inverted: the surprising behaviour is on by default and invoke's documented
behaviour is what you have to ask for.

The alternative the user described, from another project: an environment variable that, when absent,
leaves the tool completely stock, and when present patches `run` with an overload carrying the
original's whole interface plus reporting options — a delimited report line rather than dotted
alignment, and optionally stdout/stderr to a file (their driver there was Windows, where UTF-8 and
PowerShell disagree).

This plan adopts that shape, with one addition that resolves the argument the current design was
built on.

## The measurement that produced fold-by-default, and why it does not require it

`contributing/quality-gate.md` records the decision: fold by default, because "opt-in quiet would
have left the piping where it was — the session that pipes is the one that never reaches for a
flag." The evidence was 812 of 1,396 `inv quality.*` runs piped through `head`/`tail` over the week
to 2026-09-05, 58%.

**Every one of those runs was an agent session** — the corpus was 60 sessions and 14,611 Bash calls
from `~/.claude/projects/*.jsonl`. That population already runs under an environment this machine
controls: `power-user-linux-setup`'s `[packages.claude-code]` ships a `zshenv` snippet, guarded on
`CLAUDECODE`, that sets `PIPE_FAIL` for exactly these shells and nothing else.

So the flag does not have to be reached for. It is set by the environment, for the population the
measurement was about:

| who               | environment           | what they get              |
| ----------------- | --------------------- | -------------------------- |
| agent session     | env var set by zshenv | report mode, no flag typed |
| human at terminal | unset                 | stock invoke               |
| CI                | unset                 | stock invoke, full log     |

[DECISION: **flip the default to stock invoke and set the env var for agent shells**, rather than
keeping fold-by-default. The current design conflated "the default" with "what agents get" because
it had no mechanism to separate them; that mechanism already exists on this machine and already
carries `PIPE_FAIL` for the same population and the same reason. Both requirements are then
satisfied at once — least surprise for humans and CI, no flag to reach for in the sessions that were
piping.]

[DECISION: CI stays stock deliberately. A GitHub Actions log is scrolled by a human reading a
failure, and full streaming is what belongs there. Nothing about the piping measurement applies to
CI, which never pipes.]

## Design

### 1. `runner.py` — a `Local` subclass, installed only when the env var is set

Invoke's own extension point, not a monkeypatch: `Context.run` does
`self.config.runners.local(self)` (`invoke/context.py:121`), and the stock config already holds a
class there (`invoke/config.py:495`, `"runners": {"local": Local}`). So
`ns.configure({"runners": {"local": ReportingLocal}})` is supported usage, not a hack.

The mechanism was proven before this plan was written: a probe ran it against invoke 3.0.3 on Python
3.14 with a failing 25-line command, an explicit `hide=False` call and an internal `hide=True` query
in one task. All four claims held — the subclass intercepts `c.run` with zero call-site changes,
sees raw kwargs, can force `hide`, and replays more than `UnexpectedExit`'s 10-line cap.

[UNVERIFIED: that probe was a scratchpad `tasks.py`, thrown away. Nothing in this repo's suite
covers the mechanism until `tests/unit/test_runner.py` exists — see Verification.]

`__init__.py`, at the end, and only then:

```python
if os.environ.get("REPO_TASKS_RUN_REPORT"):
    ns.configure({"runners": {"local": ReportingLocal}})
```

[DECISION: **env var only, checked at import, and nothing is configured when it is unset.** That
makes "without the env var, invoke behaves exactly as documented" provable by reading five lines
rather than by arguing about a runtime branch. An `invoke.yaml` opt-in would require installing
`ReportingLocal` unconditionally and deciding per run, since the config file is not loaded when
`__init__.py` imports — which costs the provable claim for a case nobody has asked for. Left out;
add it only if a repo genuinely wants report mode permanently.]

[DECISION: drop `quality.verbose` and the `ns.configure({"quality": {"verbose": False}})` key. The
new switch is package-wide rather than gate-scoped, and a second way to say the same thing is what
the least-surprise complaint is about.]

### 2. The trigger is `echo=True`, so the report line replaces the echo line

The runner must not report every command — `gitflow.py`'s `git rev-parse` plumbing would drown the
output. The repo already draws exactly the right line, in `contributing/task-module-conventions.md`:
`echo=True` marks a command with an effect that the caller should see; internal queries use
`hide=True` and are not echoed.

So `ReportingLocal.run` reports when `kwargs.get("echo")` is set, and delegates untouched otherwise.
No list to maintain, no per-call annotation, and every future task gets reporting for free by
following the echo convention that already exists.

[DECISION: this is what makes the change uniform where the landed one was not. All ~90 call sites
get consistent treatment from one rule, instead of eleven of them getting it from an explicit
`run_step` wrapper.]

### 3. Per-call opt-out with invoke's own interface, no added kwargs

`test.coverage` must stream (its output _is_ the report) and `deps.lock` should (a human watches
it). Adding a kwarg is not available: `_unify_kwargs_with_config` raises `TypeError` on any leftover
key (`invoke/runners.py:558`), so a call site passing an extra option would break under stock invoke
— which is the whole thing this plan is protecting.

The runner instead folds only when the caller did not mention `hide` at all. A call site that must
stream passes `hide=False` explicitly. That is stock invoke's own interface, is a semantic no-op
under normal invoke (the config default is already `False`), and needs no new vocabulary. Verified:
`"hide" in kwargs` distinguishes an explicit `hide=False` from an absent one, because the runner
sees raw kwargs before invoke normalises them.

[PITFALL: `hide=False` reads as redundant and a later reader will delete it, silently folding the
coverage report. Each of the two or three sites needs a comment saying it is load-bearing in report
mode, and a test asserting it.]

### 4. The line format — delimited, command first

Dotted alignment goes. It buys an agent nothing, and `_STATUS_COLUMN = 56` is a magic number with a
comment apologising for commands that overrun it.

```
ruff check . | ok | 0.4s
pytest | ok | 4.5s | 465 passed
basedpyright | FAIL | exit=1 | 3.1s
<everything basedpyright printed>
quality.check: PASS | 11 steps | 465 passed | 8.0s
```

[DECISION: **command first, status second**, against the `FAIL | exit=127 | 20s | …` shape proposed.
Command-first is pre-printable: the runner writes `basedpyright |` before starting and completes the
line after, so a hung or killed step names itself. Status-first cannot do that, and a silent hang is
exactly what cost this package five days on `docker login`. Greps stay clean either way —
`rg '\| FAIL \|'`. This one is worth confirming, since the other shape was the one asked for.]

The verdict stays the last line of a gate run, which is the property that made `| tail -3`
survivable on a red run.

### 5. What survives from `steps.py`

- `_Ledger` and `verdict(gate)` stay. The ledger is fed by the runner instead of by `run_step`;
  `verdict` prints nothing when report mode is off, so `check`'s body is silent under stock invoke.
- `run_step` is deleted, and its eleven call sites revert to `c.run(cmd, echo=True)`.
- **`ok=frozenset({0, 5})` moves back to `testing.py`.** pytest's exit 5 being a pass is
  correctness, not display, and must hold in both modes; absorbing it into a display wrapper was a
  mistake independent of everything else here.
- The pytest count moves to `testing.py`, which parses its own tool's output and calls
  `steps.note("465 passed")` — a no-op when report mode is off.

### 6. Failure handling

On a non-zero exit with report mode on, the runner replays the captured output in full, prints the
FAIL line, and raises `Exit(code)`.

[DECISION: `Exit` rather than re-raising `UnexpectedExit`, but the contract change is now scoped to
report mode instead of being unconditional. `UnexpectedExit.__str__` prints only the last ten lines
of hidden output inside a "Encountered a bad command exit code!" template
(`invoke/exceptions.py:106-136`), so letting it through would append a lossy duplicate after the
full replay. Under stock invoke — the default — `UnexpectedExit` propagates exactly as it always
has.]

`warn=True` means the caller owns the exit code, so the runner prints the line and returns without
raising, leaving `testing.py` to decide.

[NEEDS CLARIFICATION: with that rule, a pytest run that exits 5 prints `pytest | FAIL | exit=5`
before `testing.py` accepts it as a pass. Cosmetic, and only reachable in a consumer repo with no
tests yet. Options: live with it, have the runner print `exit=5` with no FAIL token whenever
`warn=True` was passed, or give the runner a declarative tolerated-exit map. Leaning on the second —
`warn=True` already means "this exit code is not necessarily an error".]

### 7. Second axis, deferred: per-step logs to files

`REPO_TASKS_RUN_LOG_DIR=<dir>` writes each reported step's output to `NNN-<slug>.log`, written with
an explicit `encoding="utf-8"` so the console codepage is never consulted, and appends
`| log=<path>` to the report line. On failure the inline replay becomes a bounded tail plus the
path.

[DEFERRED: build this only when there is a reason. The Windows/PowerShell encoding problem that
motivated it in the other project does not exist here — this family is Linux — so the remaining
argument is context economy on a failing step, and a failure is the one moment an agent actually
wants the output inline. Recorded because the axis is real and orthogonal, not because it is owed.]

### 8. The half that belongs to another repo

`power-user-linux-setup`'s `[packages.claude-code]` zshenv snippet gains
`export REPO_TASKS_RUN_REPORT=1` beside its existing `PIPE_FAIL`, under the same `CLAUDECODE` guard.
Without it this change is a pure regression against the piping measurement — report mode would exist
and no agent session would be in it.

[DECISION: filed as its own plan for that repo rather than edited from here, per the rule against
writing into another repo's tree. **This plan is not landable until that one has landed**, which is
what `depends_on` is for once this reaches `planned`.]

## Open questions

[NEEDS CLARIFICATION: the env var name. `REPO_TASKS_RUN_REPORT` states ownership and subject. An
`INVOKE_`-prefixed name is available and would read as native, but invoke maps `INVOKE_<KEY>` onto
declared config keys, so the prefix would claim an ownership it does not have.]

[NEEDS CLARIFICATION: whether to do this as a revert-and-redo or as an evolution of the pushed
commits. The landed work is four hours old and already on `main`; roughly half of `steps.py`
survives either way. Evolution keeps the ledger and verdict history intact and is what the commit
split below assumes.]

## Known costs, recorded so they are not rediscovered

[PITFALL: a swapped Runner is invisible at the call site. Someone debugging "where did my output go"
has no local clue in `quality.py` — the answer is an env var set in a shell profile in another repo.
This is the price of the zero-call-site-churn property and it is not fully mitigable; documenting it
in `task-module-conventions.md` beside the echo rule is the best available.]

[PITFALL: `Context.sudo` also resolves through `config.runners.local` (`invoke/context.py:200`), so
it gets the same treatment. Harmless here — nothing in this package shells out through `sudo` — but
a consumer that does will see its sudo calls reported.]

[PITFALL: a consumer that hand-builds its own `Collection` from individual modules instead of
`from repo_tasks import ns` never receives the `ns.configure` call and so never gets report mode,
with no error. Identical to the gap `quality.verbose` already has, and identical in its fix: declare
it on your own root collection. Reaching those consumers would mean patching
`Config.global_defaults`, which is the unsupported monkeypatch this design avoids.]

## Files touched

- `src/repo_tasks/runner.py` — new, `ReportingLocal`.
- `src/repo_tasks/steps.py` — keep the ledger and `verdict`, delete `run_step`, add `note`.
- `src/repo_tasks/__init__.py` — env-gated `ns.configure`, drop the `quality.verbose` key.
- `src/repo_tasks/quality.py`, `deps.py`, `docs.py`, `testing.py` — revert to
  `c.run(..., echo=True)`; restore pytest's exit-5 tolerance and its count to `testing.py`;
  `hide=False` on `test.coverage` and `deps.lock`.
- `contributing/quality-gate.md` — rewrite "What the gate prints"; the fold-by-default decision
  becomes the report-mode decision with this plan's reconciliation.
- `contributing/task-module-conventions.md` — replace the gate-step carve-out under the echo rule
  with the `echo=True`-is-the-trigger rule.
- `README.md` — the design paragraph.
- Tests: `tests/unit/test_runner.py` new; `test_steps.py`, `test_quality.py`, `test_testing.py`,
  `test_init.py` updated.

Commit split, each standing on its own:

1. Restore pytest's exit-5 tolerance and count parsing to `testing.py` (correctness, no mode).
2. Add `runner.py` and the env-gated install; keep `run_step` working alongside it.
3. Revert the eleven call sites to `c.run(echo=True)`; delete `run_step`.
4. Docs.

`interactive.py` and the `docker.login`/`helm.login` change are untouched by all of this. That was a
real hang on the interpreter this ships on, the fix is correct, and stepping outside invoke there is
not a least-surprise question — it is the only way those tasks work at all.

## Verification

- The probe behind §1 was a scratchpad `tasks.py`, not a test. It becomes
  `tests/unit/test_runner.py`: a `Local` subclass intercepting a failing multi-line command, an
  explicit `hide=False`, and an internal `hide=True` query, asserting the report line, the full
  replay, and that the last two are passed through untouched.
- The property that actually matters and that a `MockContext` cannot see: **with the env var unset,
  output is byte-identical to invoke's.** Capture `inv quality.lint-check` before and after the
  change with the var unset and diff them.
- `INVOKE_QUALITY_VERBOSE` must stop being read anywhere — `rg INVOKE_QUALITY_VERBOSE` returns
  nothing outside retired plans.
- Re-run the red-gate check from `quality-gate.md`'s pipefail pitfall: with report mode on,
  `inv quality.check 2>&1 | tail -3` shows the failing command and exits non-zero.

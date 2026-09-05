---
status: in-progress
updated: 2026-09-05
depends_on: [scaffoldapy]
---

# Run reporting as an opt-in agent mode, not as invoke's new default

## Context

**This supersedes layer 2 of a four-layer design in another repo, which was not known to this
session while it worked.** `agent-skills`' `plans/2026-09-05-a-piped-gate-that-cannot-lie.md`
(`status: planned`) specifies fold-by-default with a flag to restore streaming, and records the
landed `ba9e8e6`..`4c0bd3a` as satisfying it. That parent plan, and
`2026-09-05-quiet-gate-changes-what-the-instruments-see.md` filed against the same repo, both still
describe the old mechanism; the correction is filed for them as
`2026-09-05-layer-2-was-replaced-after-the-parent-plan-recorded-it.md`. Two consequences belong here
rather than there: the week-later `audit.py --compare` that plan schedules cannot be read until the
`power-user-linux-setup` export lands, and layer 2's stated "the verdict survives in CI logs"
property is deliberately dropped by §8's decision — see that filing's open question.

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

It is now covered by `tests/unit/test_runner.py`, which runs real subprocesses rather than a
`MockContext` for exactly the reason the `docker login` hang gives.

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
ruff check . | ok | 0.0s | All checks passed!
ruff format . | ok | 0.0s | 1 file reformatted
dprint check --config-discovery=ignore-descendants | ok | 0.1s
basedpyright | ok | 2.5s | 0 errors, 0 warnings, 0 notes
uv lock --check | ok | 0.0s | Resolved 64 packages in 1ms
pytest | ok | 1.4s | 592 passed in 1.30s
```

[DECISION: **command first, status second**, against the `FAIL | exit=127 | 20s | …` shape proposed
— confirmed by the user 2026-09-05. Command-first is pre-printable: the runner writes
`basedpyright |` before starting and completes the line after, so a hung or killed step names
itself. Status-first cannot do that, and a silent hang is exactly what cost this package five days
on `docker login`. Greps stay clean either way — `rg '\| FAIL \|'`.]

The verdict stays the last line of a gate run, which is the property that made `| tail -3`
survivable on a red run.

### 4a. The fourth column is the last non-empty line of the tool's own output

The user's question on reading the design — does a successful step hide its output completely,
leaving only the command and stats? Under what landed, yes. That is a real loss, and it is the same
one this plan's own critique names: `ruff format .` reformatting three files reports `ok`.

Measured rather than argued, over this repo's own gate on 2026-09-05:

| command                 | lines on success | last non-empty line             |
| ----------------------- | ---------------: | ------------------------------- |
| `ruff check .`          |                1 | `All checks passed!`            |
| `ruff format --check .` |                1 | `96 files already formatted`    |
| `ruff format .` (dirty) |                1 | `1 file reformatted`            |
| `basedpyright`          |                1 | `0 errors, 0 warnings, 0 notes` |
| `uv lock --check`       |                1 | `Resolved 64 packages in 1ms`   |
| `pytest -q`             |               10 | `592 passed in 1.30s`           |
| `dprint check`          |                0 | —                               |
| `shellcheck`            |                0 | —                               |
| `shfmt -d`              |                0 | —                               |

[DECISION: **carry the last non-empty output line onto the report line, for every tool.** Five of
nine emit exactly one line and it _is_ the summary, so nothing whatsoever is lost for those; three
emit nothing at all on success, so there is nothing to lose; pytest is the only multi-line case and
nine of its ten lines are progress noise. The answer to "does it hide the output" therefore becomes
"only where the output was progress noise" rather than "yes".]

[DECISION: this **replaces** the pytest-specific `_PYTEST_COUNT_RE` parser and the
`contributing/quality-gate.md` decision that pytest's count is "the only number read out of a tool's
output". A generic tail line reads no tool's format, so there is nothing to break when a tool
changes its summary — it is one line either way — and `steps.note` is no longer needed at all.
Strictly less machinery than what landed, and it covers eight more commands.]

[PITFALL: the tail line is only meaningful because these tools are quiet on success. A chatty
command would put its least interesting line there. That is acceptable — the line is a hint beside
`ok`, never the record — but it is the reason the log-file axis in §7 exists rather than being
dismissed.]

### 5. What survives from `steps.py`

- `_Ledger` and `verdict(gate)` stay. The ledger is fed by the runner instead of by `run_step`;
  `verdict` prints nothing when report mode is off, so `check`'s body is silent under stock invoke.
- `run_step` is deleted, and its eleven call sites revert to `c.run(cmd, echo=True)`.
- **`ok=frozenset({0, 5})` moves back to `testing.py`.** pytest's exit 5 being a pass is
  correctness, not display, and must hold in both modes; absorbing it into a display wrapper was a
  mistake independent of everything else here.
- `_pytest_summary`, `_PYTEST_COUNT_RE` and the planned `steps.note` all go — §4a's generic tail
  line does the job for every command, not just pytest's.

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

[DECISION: on a `warn=True` call the runner prints `exit=N` **without** a `FAIL` token, because
`warn=True` already means "a non-zero exit here is not necessarily an error" and the caller is about
to decide. So a pytest run in a repo with no tests reads `pytest | exit=5 | 0.1s | no tests ran`
rather than claiming a failure the gate then ignores. The alternative — a declarative tolerated-exit
map on the runner — was rejected as a second place where "which exit codes are OK" lives, when
`warn=True` already says it at the call site.]

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

### 9. `runner.configure(ns)` — the half a consumer with its own `Collection` has to call

§1's `ns.configure` is on **`repo_tasks`' own `ns`**. A consumer that hand-builds its Collection —
`power-user-linux-setup` does, and `scaffoldapy`'s template generates one — never touches that
object, so the configure never runs. The variable is set, `runner.enabled()` is true, and the gate
prints stock invoke output with nothing anywhere saying the mode is off.

Observed live 2026-09-05 from `power-user-linux-setup`'s session
(`25ea8788-b99d-43a2-9611-2d0c1f207694.jsonl`, around 18:20Z), in this order, which is why it is
recorded as a finding rather than as a reading of the code:

1. The `CLAUDECODE`-guarded `zshenv` snippet gained `export REPO_TASKS_RUN_REPORT=1`, deployed with
   `inv zsh.configure`.
2. `env | rg REPO_TASKS_RUN_REPORT` in a fresh agent Bash call returned it set.
3. `inv quality.precommit` printed stock invoke output — every command echoed, every line streamed,
   no verdict.
4. Nothing anywhere reported that the mode was off. There is no warning, no probe, and no way to
   tell "the variable is unset" from "the variable is set and unreachable" by looking at the output.
5. Adding the same one line to that repo's own namespace produced the expected shape immediately:
   `quality.check | PASS | 11 steps | 6.1s`.

[DECISION: **ship `runner.configure(ns)`** — one import and one call, owning both the `enabled()`
check and the `{"runners": {"local": ReportingLocal}}` key, so no consumer re-derives either and a
later change to the mechanism does not need every consumer edited. Chosen by the user 2026-09-06
over two alternatives. A documented one-liner — cheapest, and honest about the consumer owning its
own Collection — was rejected because it is exactly the state that produced this finding. Something
that _notices_ was rejected as a new print: a consumer running its gate with the variable set and
the runner unconfigured is a detectable state, but a warning on every gate run of every repo that
has not opted in is worse than the silence. It stays available as an addition to an existing
diagnostic if the silence bites a second time.]

[PITFALL: **the helper does not close the gap, it only gives the fix a name.** A consumer that never
calls it is exactly as silent as before. That is the price of not patching `Config.global_defaults`,
the unsupported monkeypatch this whole design avoids, and it is why reaching the consumers is sweep
work rather than something this package can settle on its own.]

[PITFALL: `power-user-linux-setup` wrapped the line in a local helper rather than reading the two
attributes inline, for a reason worth knowing before writing the call anywhere else: that repo's
optional-import helper returns Nones-or-modules, which widens to `Any` under `basedpyright`, so
reading `runner.enabled` and `runner.ReportingLocal` off that value fails its own gate. A single
`configure(ns)` imported directly is the shape that type-checks.]

**`scaffoldapy`'s template is the multiplier**, and it is why this is a design section rather than a
line in the sweep. Every repo generated from it builds its own Collection, so every generated repo
is in this state at birth — and the population the whole design exists to reach, agent sessions
running a consumer's gate, is exactly the population that gets nothing. `power-user-linux-setup` is
one repo somebody noticed; the template keeps producing more. That is the same "true of the repo's
own tree, false of what it generates" shape
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) records for
`failOnWarnings`, arriving in a change that has no config file and no dependency-group entry, so
neither half of `configs.diff` can see it.

[DEFERRED: whether `scaffoldapy`'s template should carry the call by default. For: it is the only
place that stops the population growing, and a generated repo's owner has no reason to suspect the
mode exists. Against: it puts an agent-oriented departure into every generated repo's
`tasks/__init__.py`, where a human reader meets it first — the same least-surprise objection that
inverted this design in the first place. **Not this repo's call**, which is why it is deferred here
rather than left as an open question: filed for `scaffoldapy`, which has its own session and its own
plans, and named in this plan's `depends_on`.]

[DEFERRED: nothing measures whether report mode actually moves the piped-gate rate. The truthfulness
property is what the design is for and is already achieved; a rate change would be a bonus.
`power-user-linux-setup`'s `plans/2026-09-05-pipefail-in-the-agent-shell.md` owns that measurement
and names the baseline to compare against.]

This section is merged in from `2026-09-05-report-mode-reaches-no-consumer-by-itself.md`, filed for
this repo from that session and absorbed 2026-09-06 — the name to search for with `plans.py archive`
if the original filing is ever wanted.

## Settled while drafting

[DECISION: the env var is `REPO_TASKS_RUN_REPORT`, stating ownership and subject. An
`INVOKE_`-prefixed name would read as native and is exactly why it was rejected: invoke maps
`INVOKE_<KEY>` onto its own declared config keys, so the prefix would claim an ownership it does not
have.]

[DECISION: evolve the pushed commits rather than revert-and-redo. The landed work is hours old and
already on `main`; roughly half of `steps.py` — the ledger and `verdict` — survives either way, and
a revert would put the same code back through history twice. Chosen by the user 2026-09-05.]

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
with no error. Predicted here as "identical to the gap `quality.verbose` already has, and identical
in its fix: declare it on your own root collection" — **the prediction was right about the gap and
wrong about the fix being one line a consumer can just write**, which §9 records after hitting it
live. Reaching those consumers without their cooperation would mean patching
`Config.global_defaults`, the unsupported monkeypatch this design avoids, so the gap is real and
what §9 ships is a named call rather than a closure.]

## Files touched

Landed 2026-09-05 in three commits, not the four planned: commits 1 and 3 below could not be
separated without a red intermediate, because deleting `steps.py` needs the call sites reverted and
`runner.py` present in the same state, and `test.untested_modules` fails the moment a module loses
its test file.

1. **`runner.py` + `tests/unit/test_runner.py`**, used by nothing yet — so the switchover commit is
   only a switchover, and the new file can be read against the stock `Local` it replaces. Verified
   green on its own with the old `steps.py` still in place (605 tests, both suites).
2. **The switchover**: the eleven call sites in `quality.py`/`deps.py`/`docs.py` back to
   `c.run(..., echo=True)`; `testing.py` regains pytest's exit-5 tolerance and passes `hide=False`
   on the streaming tiers; `__init__.py` installs the runner behind the env var and drops the
   `quality.verbose` key; `steps.py` and `test_steps.py` deleted; `test_deps.py`, `test_docs.py`,
   `test_init.py`, `test_quality.py`, `test_testing.py` updated.
3. **Docs**: `contributing/quality-gate.md`'s "What the gate prints" rewritten around two modes, the
   echo rule in `contributing/task-module-conventions.md`, `README.md`'s design paragraph, and three
   stale `steps.py` citations repointed.

`interactive.py` and the `docker.login`/`helm.login` change are untouched by all of this. That was a
real hang on the interpreter this ships on, the fix is correct, and stepping outside invoke there is
not a least-surprise question — it is the only way those tasks work at all.

## Verification

All four ran on 2026-09-05, against this repo's own gate.

- **`tests/unit/test_runner.py`**, 13 tests on real subprocesses rather than a `MockContext` — the
  module is about what output and exit codes turn into, and a mock supplies both. Covers the report
  line, the full replay, the `warn=True` path, the untouched `hide=True` query, the load-bearing
  `hide=False`, elision, the verdict, and that stock invoke still raises `UnexpectedExit`.
- **With the env var unset, output is invoke's own.** `inv quality.precommit` prints invoke's bold
  echo and every tool's full output, and a red `inv quality.check` ends with ruff's own diagnostic
  and no verdict line.
- **With it set**, the same gate prints fifteen report lines and
  `quality.precommit | PASS | 15 steps | 4.6s`, and the summary column carries real content:
  `96 files left unchanged`, `0 errors, 0 warnings, 0 notes`, `Resolved 64 packages in 1ms`,
  `No findings to report. Good job! (15 suppressed)`.
- **The red-run property from `quality-gate.md`'s pipefail pitfall.**
  `REPO_TASKS_RUN_REPORT=1 inv quality.check 2>&1 | tail -3` on a deliberately unlint-clean file
  ended with `FAIL | ruff check . | exit=1 (output above)` and the Bash tool reported exit 1.
- `rg INVOKE_QUALITY_VERBOSE` returns nothing outside this plan.

### §8's other half landed the same evening, and it works

`power-user-linux-setup` took the filed plan and extended its `CLAUDECODE`-guarded `zshenv` snippet
to two statements:

```shell
if [ -n "${CLAUDECODE:-}" ]; then
  setopt PIPE_FAIL
  export REPO_TASKS_RUN_REPORT=1
fi
```

Verified end to end 2026-09-05 evening, in an agent session that set nothing by hand:

- `env` in a Bash call shows `REPO_TASKS_RUN_REPORT=1` and `setopt` shows `pipefail`.
- A bare `inv quality.precommit` in this repo prints fifteen report lines and
  `quality.precommit | PASS | 15 steps | 4.9s`.
- **In a consumer**: `inv quality.lint-check` in `power-user-linux-setup`, whose `uv.lock` pins
  `repo-tasks` at `7bb880b`, prints `ruff check . | ok | 0.0s | All checks passed!` — **but only
  because that repo added the wiring to its own `tasks/__init__.py` first.** The export alone did
  nothing there.

[PITFALL: **the environment half is not the whole change, and the gap is silent in both
directions.** This plan predicted it in §"Known costs" and still recorded the export as the
remaining half; a session hit it live on 2026-09-05 before the prediction was connected to the
filing, which is the whole reason §9 exists. **Read §9 before treating any consumer as done** — the
line above is evidence about a consumer that had already added its own wiring, not about what the
export does on its own.]

[PITFALL: **no session restart is needed, and a session that assumes one will wait for nothing.**
Each Bash call is a fresh non-interactive `zsh -c` that reads `~/.zshenv` every time, so a deployed
snippet reaches the _running_ session's next call. This plan's own author predicted the opposite in
a report — "existing agent sessions keep the old environment until they're restarted" — and was
wrong; `setup.toml`'s comment on that field had said so all along. It is the same shape as the
`SSH_AUTH_SOCK` export that does _not_ survive between calls, which is probably where the wrong
intuition comes from: an `export` typed **in** a call dies with it, while one in `~/.zshenv` is
re-read by every call.]

[DEFERRED: the remaining consumers. `power-user-linux-setup` is verified; `scaffoldapy`-generated
repos and the `*-polite-mcp` family take `repo-tasks` as a pinned dependency and none has been
bumped. `contributing/consumer-sweep.md` owns that sequence, and an `agent-skills` plan
(`sweep-misses-downstream-consumers-of-a-pushed-library.md`) names this very session as its
example.]

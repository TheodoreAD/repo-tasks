---
status: landed
updated: 2026-09-05
source_repo: github.com-personal/agent-skills
source_session: 4e6fc3cc-eebb-4ea1-b035-ca0112dc9982.jsonl
source_moment: 2026-09-04T22:17:38Z
---

# A quiet gate whose last line is the verdict

## Context

Layer 2 of `agent-skills`' `plans/2026-09-05-a-piped-gate-that-cannot-lie.md`, which owns the design
and the measurements. The decision it rests on, taken with the user 2026-09-05: the fix for agents
piping the gate through `tail` is not another rule (four rewordings, each measured null) but
removing what the pipe buys.

Over the seven days to 2026-09-05, across every consumer of this package (60 main sessions, 14,611
Bash calls): **812 of 1,396 `inv quality.*` runs were piped through `head`/`tail` — 58%** (65% in
`agent-skills` sessions, 64% in `ingesta`, 58% in `repo-tasks`, 41% in `power-user-linux-setup`).
466 of the 812 asked for the last 3 to 8 lines. Measured live in `agent-skills` the same day,
`inv quality.precommit` prints about 50 lines on success: every command echoed twice (`fix` then
`check` run the same linters), zizmor's banner, `uv lock`'s resolution line, pytest's header and 25
lines of dots. The line the session wants is the last one. The gate is also the single largest
`exit-masked` shape machine-wide (31% of 2,646 such calls), and a `| tail -N` returns `tail`'s 0
whatever the gate did.

## What to do

Adopt `pre-commit run`'s output shape, the tool this gate replaces:

```
ruff check . ……………………………… ok  0.4s
ruff format --check . ………… ok  0.2s
basedpyright …………………………… ok  3.1s
pytest ……………………………………… ok  4.5s  465 passed
quality.precommit: PASS  12 steps, 465 tests, 14.2s
```

and on failure:

```
basedpyright …………………………… FAIL  exit 1
<the step's captured output, in full>
quality.check: FAIL  type_check exited 1 (output above)
```

- Each step runs `c.run(cmd, hide=True, warn=True)`; the command line is still printed, so the
  module docstring's "every command is echoed so both a human and an agent see exactly what ran"
  survives — only a successful step's output is folded. A failing step's captured stdout+stderr is
  replayed whole before the verdict, and the task exits with that step's code as today.
- **The verdict is the last line, and it names the failing step.** That is the property that matters
  more than the line count: a `| tail -3` on a red run then shows `FAIL type_check` rather than
  invoke's generic "Encountered a bad command exit code" wrapped around whatever the step printed,
  and it stays true on a machine without the shell change layer 1 makes.
- **Quiet by default, `--verbose` streams** (decided with the user 2026-09-05). Opt-in quiet would
  leave the 58% where it is: the session that pipes is the one that never reaches for a flag. Invoke
  pre-tasks take no arguments, so the flag is read once (an env var such as `REPO_TASKS_VERBOSE=1`,
  or `c.config`) by the step runner rather than threaded through the chain.
- The pytest count for the verdict line comes from the captured summary (`N passed`), which is also
  the line that `tail -3` was reaching for.
- CI logs get the same output; a failing step's full output is still there, and a green run's log is
  a dozen lines instead of a screen per repo.

## Evidence

- Design, the machine-wide numbers, and the probe of what `pipefail` does to these shapes:
  `agent-skills` `plans/2026-09-05-a-piped-gate-that-cannot-lie.md`.
- The user's framing, 2026-09-05, in the `agent-skills` session named above: _"ruminate deeply on
  how we can solve this, it's disruptive and can lie about a lot of things."_
- The adherence watch in `power-user-linux-setup`
  (`plans/2026-08-23-global-agents-md-adherence-watch.md`, sessions 9 and 10) raised "the fix is a
  quieter gate, not a better rule" on 2026-08-30 as an open question; this is that question answered
  with a week of data.
- Same-repo precedent: the 1 MB basedpyright output that drove the redirect-and-`echo $?` habit was
  fixed at the source (`failOnWarnings: true`, `contributing/type-checking.md`), and the habit went
  to zero — recorded in `power-user-linux-setup`'s `contributing/global-agents-md.md`, "Composing a
  Bash call".

## Open questions

[DECISION: only pytest reports a number, read from its closing summary line (`N passed`, `N failed`,
`N errors`); every other step reports ok/FAIL and wall time, measured around the call rather than
parsed from anything. Settled in the implementation 2026-09-05.]

## Recommended direction

Implement in `src/repo_tasks/quality.py` with tests asserting the folded/replayed output and the
verdict line; document the shape in `contributing/`. Lands after layer 1 (`power-user-linux-setup`
pipefail snippet) and layer 3 (`agent-skills` scripts), with a `session-bash-audit` baseline saved
before it so its effect on the 58% is measured on its own.

## Migrated to

Landed 2026-09-05, one day after filing, with layer 1 live and layer 3 not yet landed — so the
per-layer measurement the plan asked for waits on layer 3, and the baseline saved after layer 1
(`~/.local/state/session-bash-audit/2026-09-05-pipefail-live.json`) is the one this change is
measured against.

- The shape and its mechanics: `src/repo_tasks/steps.py` (module docstring), which every gate step
  in `quality.py`, `testing.py`, `deps.py` and `docs.py` runs through, and
  `tests/unit/test_steps.py` for the folded/replayed/verdict contract.
- Every decision — fold by default with `INVOKE_QUALITY_VERBOSE=1` to stream, the verdict naming the
  command rather than the task, `precommit` inlining `check`'s steps, verbosity as invoke config on
  the root collection, pytest as the only parsed output, which pytest tiers fold — and the two
  pitfalls (stream flushing under `2>&1 |`, pipefail and this change covering different halves):
  `contributing/quality-gate.md`, "What the gate prints".
- The echo rule's carve-out for gate steps: `contributing/task-module-conventions.md`, "Echo every
  command that does something". The README's design paragraph describes the new shape.

Not migrated: the machine-wide measurements in Context, which `agent-skills`'
`plans/2026-09-05-a-piped-gate-that-cannot-lie.md` owns and will carry into that skill's research
notes when its own layers land; the numbers that justify this repo's decision are quoted in the
`[DECISION:` above. The recommended-direction note that the design shape is `pre-commit run`'s
survives as the first sentence of the new contributing section.

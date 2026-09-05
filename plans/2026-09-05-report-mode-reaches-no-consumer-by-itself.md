---
status: idea
updated: 2026-09-05
source_repo: github.com-personal/power-user-linux-setup
source_session: 25ea8788-b99d-43a2-9611-2d0c1f207694.jsonl
source_moment: 2026-09-05T18:20:00Z
---

# Setting `REPO_TASKS_RUN_REPORT` turns report mode on for `repo-tasks` and for nobody else

## Context

`plans/2026-09-05-run-reporting-as-an-opt-in-agent-mode.md` filed the environment half of its design
for `power-user-linux-setup`, whose plan called the export "the whole change". **It is not, and the
gap is silent in both directions**, which is what makes it worth a plan rather than a line in a
commit.

Report mode is switched on in `src/repo_tasks/__init__.py`:

```python
if runner.enabled():
    ns.configure({"runners": {"local": runner.ReportingLocal}})
```

That is on `repo_tasks`' own `ns`. A consumer that builds its own `Collection` — importing the
modules it wants and adding them itself, which is what `power-user-linux-setup`'s
`tasks/__init__.py` does and what `scaffoldapy`'s template generates — never uses `ns`, so the
configure never runs. The variable is set, `runner.enabled()` is true, and the gate prints stock
invoke output.

## Evidence

Observed live 2026-09-05, in this order, which is why it is stated as a finding rather than as a
reading of the code:

1. `[packages.claude-code]`'s `zshenv` snippet gained `export REPO_TASKS_RUN_REPORT=1` under the
   existing `CLAUDECODE` guard, deployed with `inv zsh.configure`.
2. `env | rg REPO_TASKS_RUN_REPORT` in a fresh agent Bash call returned it set.
3. `inv quality.precommit` printed stock invoke output — every command echoed, every line streamed,
   no verdict.
4. Nothing anywhere reported that the mode was off. There is no warning, no probe, and no way to
   tell "the variable is unset" from "the variable is set and unreachable" by looking at the output.
5. Adding the same one line to that repo's own namespace produced the expected shape immediately:
   `quality.check | PASS | 11 steps | 6.1s`.

Both halves were then verified end to end together with `PIPE_FAIL`, which is the pairing the design
turns on: a deliberately failing step piped to `tail -3` exits 1 **and** its last line reads
`FAIL | basedpyright --pythonversion 3.6 | exit=1 (output above)`.

## Why it matters more than one line of consumer wiring

**`scaffoldapy`'s template is the multiplier.** Every repo generated from it builds its own
collection, so every generated repo is in this state at birth, and the population the whole design
exists to reach — agent sessions running a consumer's gate — is exactly the population that gets
nothing. `power-user-linux-setup` is one repo somebody noticed; the template keeps producing more.

That is the same "true of the repo's own tree, false of what it generates" shape
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) records for
`failOnWarnings`, arriving in a change that has no config file and no dependency-group entry, so
neither half of `configs.diff` can see it.

## Recommended direction

Three options, in the order they seem worth considering:

1. **A documented one-liner, and say it in `contributing/quality-gate.md`'s "What the gate
   prints".** Cheapest and most honest — the consumer owns its own collection, so it owns what is
   configured on it. The cost is that it is invisible until someone reads the doc, which is exactly
   how this was found.
2. **A helper the consumer calls** — `repo_tasks.runner.configure(ns)`, one import and one call,
   which at least gives the line a name and a docstring rather than leaving each consumer to
   re-derive `{"runners": {"local": ...}}`. `power-user-linux-setup` wrapped it locally for a reason
   worth knowing: reading two attributes off a module that its optional-import helper returns widens
   to `Any` under `basedpyright`, so the naive spelling fails that repo's gate.
3. **Something that notices.** A consumer whose gate runs with the variable set and the runner
   unconfigured is a detectable state — but a warning printed on every gate run of every repo that
   has not opted in is worse than the silence, so this only makes sense as part of an existing
   diagnostic rather than as a new print.

[NEEDS CLARIFICATION: whether `scaffoldapy`'s template should carry the wiring by default. Argument
for: it is the only place that stops the population growing, and a generated repo's owner has no
reason to suspect the mode exists. Argument against: it puts an agent-oriented departure into every
generated repo's `tasks/__init__.py`, where a human reader meets it first — which is the same "least
surprise" objection that inverted this design in the first place. Not this repo's call alone;
`scaffoldapy` has its own session and its own plans.]

[DEFERRED: nothing here measures whether report mode actually moves the piped-gate rate. The
truthfulness property is what the design is for and is already achieved; a rate change would be a
bonus. `power-user-linux-setup`'s `plans/2026-09-05-pipefail-in-the-agent-shell.md` owns that
measurement and names the baseline to compare against.]

---
status: idea
updated: 2026-08-30
---

# Gate candidates offered during the coverage sweep and not taken

## Context

The 2026-08-26 sweep asked which classes of problem `quality.check` did not look for at all, and
adopted a tool for each concern that earned one — the result is
[`../contributing/quality-gate.md`](../contributing/quality-gate.md). Two candidates were evaluated,
found genuinely useful, and still not adopted. Both are recorded here rather than in that file
because they are wanted, not rejected: what is written there is the settled half.

### deptry

Run ad hoc during the sweep and it earned its keep immediately. Adopting it means a permanent
dependency in every consumer plus per-repo false-positive configuration, which the shipped-config
model has nowhere to put. Re-run by hand when dependencies change.

What it found, so the next run is not a surprise:

- `bump-my-version` and `repo_tasks` (twice — the dogfooding self-import) are false positives:
  shelled out, and self-referential, respectively.
- `python-dotenv` is reported unused and genuinely is (`rg dotenv` over `src/`, `tests/`, `tasks.py`
  returns nothing). It stays: a deliberate forward-looking dependency for local `.env`-based
  configuration of task options. **Not a defect, and not to be "cleaned up" by a future pass.**

[PITFALL: deptry does not check dependency groups for unused entries at all, so it would never have
caught a stale `repo-tasks-quality` entry — which is the thing that motivated looking at it in the
first place.]

### ruff `S602` / `S603` / `S607`

The non-noise slice of bandit, relevant precisely because shelling out is what this package does.
Offered during the sweep and not taken; the whole `S` family stays correctly rejected as noise, and
this is the argument for carving three rules out of that rejection rather than reversing it.

## Measured, 2026-08-30

Both runs the "Recommended direction" asked for, done. Neither took more than a minute, and both
came back differently from what the questions assumed.

### deptry: 4 findings, 0 defects

`deptry .` against a clean tree, with no configuration of any kind — it scanned 22 files and needed
nothing set up:

| finding                                                             | verdict                                         |
| ------------------------------------------------------------------- | ----------------------------------------------- |
| `DEP002` `python-dotenv` defined but not used                       | the deliberate forward-looking dependency above |
| `DEP002` `bump-my-version` defined but not used                     | shelled out, invisible to import analysis       |
| `DEP003` `repo_tasks` imported as transitive (`tasks.py:10`, `:11`) | the dogfooding self-import                      |

Exactly the set the sweep recorded four days earlier, so nothing has drifted. The useful number is
the ratio: **4 findings, 0 defects.** A consumer handed this as a gate step meets a red gate on its
first run, before it has written a line of its own configuration.

The two shapes are not equally cheap to silence, which the original question missed. `DEP002` is a
per-package entry in `pyproject.toml`'s `[tool.deptry]`; `DEP003` carries a real file and line and
is suppressible per occurrence. The `repo_tasks` self-import — the one finding genuinely unique to
this repo's dogfooding — is the suppressible kind.

[PITFALL: `uv run --with deptry` **deleted and recreated this repo's `.venv`** rather than layering
an overlay over it, because the tool's resolution wanted a different interpreter than the venv had.
`uv sync --all-groups` restored it and the gate came back green, but between the two the dev
environment is broken for every parallel session sharing the tree. A one-off measurement of a tool
that is not a dependency belongs in a throwaway environment —
`env -u VIRTUAL_ENV -u PYTHONPATH uv run --no-project --with deptry …` — never against the project
venv. Confirmed 2026-08-30 by doing it the wrong way.]

### ruff `S602`/`S603`/`S607`: 3 findings, and the reason matters more than the count

`ruff check --select S602,S603,S607 src/`:

```
src/repo_tasks/configs.py:67:9:   S603 `subprocess` call: check for execution of untrusted input
src/repo_tasks/configs.py:67:24:  S607 Starting a process with a partial executable path
src/repo_tasks/version.py:336:28: S607 Starting a process with a partial executable path
```

`S602` (`shell=True`) fires nowhere at all.

[PITFALL: the fear that these rules would produce a wall of `noqa` rested on a wrong premise — that
`S603` flags every `subprocess` call, "which in this package is close to every task". It is not
close to every task: there are exactly **two** `subprocess` call sites in the whole package.
Everything else shells out through invoke's `c.run()`, which flake8-bandit does not model and cannot
see. So the rules are not noisy here, they are nearly **inert** — which is the worse answer for the
same decision. A rule that cannot see the thing the package spends its life doing is not covering
the concern it was proposed for.]

That splits the question in two, and the split is new:

- **For this repo**, the three rules buy almost nothing. The shelling-out they were meant to police
  goes through a call they do not analyse.
- **For a consumer**, they may have real reach — a generated project doing its own `subprocess.run`
  is exactly the shape the rules model. That is an argument about the exported manifest, not about
  this repo's gate, and the two have been one question until now.

## Open questions

[NEEDS CLARIFICATION: adopt deptry at all, given 4 findings and 0 defects on the repo that liked it
most? The mechanism objection recorded at the time is definitively not the problem — `[tool.deptry]`
in `pyproject.toml` is a perfectly good home for the ignores, and the tool needed no config to run.
What the measurement shows instead is a per-consumer onboarding cost: every repo needs its own
ignore list before the tool is green once. That rules out "gate step on day one" on the evidence and
leaves two honest options — standalone and documented, run by hand when dependencies change, which
is what it already is; or a gate step that `scaffoldapy` seeds a starting `[tool.deptry]` for. Only
the second would be worth wiring, and it is a `scaffoldapy` change rather than a `repo-tasks` one.]

[NEEDS CLARIFICATION: do `S602`/`S603`/`S607` belong in the shipped `ruff.toml` even though they are
inert here? The measurement argues no on this repo's merits and possibly yes on a consumer's, and
the shipped config cannot distinguish the two. The next step, if this is pursued at all, is running
the same select against a generated project rather than deciding from this repo's number — which is
small for the wrong reason.]

## Recommended direction

Both measurements are in, and neither tool comes out of them looking like a gate step.

1. **Leave deptry standalone and keep the table above current**, so the next ad-hoc run is not a
   surprise — it has now reproduced identically twice. Revisit adoption only alongside a
   `scaffoldapy` change that seeds `[tool.deptry]`; without one, every consumer's first gate run is
   red for reasons that are not its fault.
2. **Do not add `S602`/`S603`/`S607` to the shipped `ruff.toml` on this repo's evidence.** If the
   consumer-side question is worth answering, measure it against a consumer.
3. Neither blocks anything. This plan's value is now the measurements rather than the decision, and
   it can sit at `idea` indefinitely without costing anything.

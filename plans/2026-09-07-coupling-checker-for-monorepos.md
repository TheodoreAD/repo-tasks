---
status: idea
updated: 2026-09-07
---

# Does the quality manifest gain a coupling checker, and on what evidence

## Context

The rule landed first: distinct distributions in one repo import each other through their installed
(editable) form, never by putting a sibling's source on the path. `ruff.toml`'s `banned-api` table
enforces the _path_ half as of `1c91c2e` — measured coverage, no new dependency, inert in a repo
with one package.

What it does not enforce is the half that matters more in a monorepo: **package A importing package
B without declaring B as a dependency.** The import succeeds locally because a uv workspace resolves
every member into one shared environment, and fails for whoever installs A's wheel. Nothing in this
family currently detects that, and the user works in monorepos often enough to want the question
settled on evidence rather than on a survey.

The survey exists already and is not repeated here — see the session of 2026-09-07 and the clones in
`$RESEARCH_HOME`. Its conclusion was that no candidate could be judged without a repo shaped like
the problem, which this repo is not: one workspace member, no cross-imports, the degenerate case.

**This plan is the missing half: a fixture, four experiments, and the decision rule to apply to
their results.** Nothing is adopted until they run.

## What the survey established, so it is not re-derived

| tool                | enforces                                                              | sees the code via                                   | health (2026-09-07)                                                      |
| ------------------- | --------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------ |
| ruff `TID251`       | any name you list — `sys.path`, `site.addsitedir`                     | its own parser                                      | already in the gate                                                      |
| import-linter/grimp | forbidden, independence, layers, protected, acyclic siblings          | `importlib.util.find_spec`, then ruff's Rust parser | 13 stable releases/yr, last 3d, `py.typed`, test/source 2.18             |
| tach                | per-module `depends_on` allowlists, layers, interfaces, external deps | source roots, no install                            | last stable release 118d ago, no `py.typed`, test/source 0.7, repo moved |
| deptry              | DEP001 missing, DEP002 unused, DEP003 transitive, DEP004 misplaced    | static scan against declared deps                   | 3 releases/yr, last 172d, 4 yanked, no `py.typed`                        |
| FawltyDeps          | undeclared/unused deps                                                | static                                              | 0 releases in a year, last push 433d — **out**                           |

One property is worth carrying forward because it decides what import-linter can even be asked:
grimp resolves root packages through `find_spec`, so it lints what is **installed**. It cannot be
the detector for a repo that reaches its siblings by path — it is the tool for the question after
that one.

## The fixture, which is the actual deliverable

None of the experiments mean anything without a repo shaped like the problem, and this repo is not
one. Build `tests/fixtures/monorepo/` (or a generated tmp tree — see the open question) with three
distributions in one uv workspace:

- `pkg-core` — no dependencies.
- `pkg-api` — declares `pkg-core`, imports it. The **legitimate** edge.
- `pkg-worker` — declares nothing, imports `pkg-core` anyway. The **undeclared** edge, which is the
  failure this whole plan is about.

Plus two more edges once the basics hold: `pkg-core` importing `pkg-api` (a **cycle** across
distributions), and `pkg-api` importing a _private_ module of `pkg-core` (`pkg_core._internal`) —
declared, so no tool that only reads dependency metadata can see it, and the case that separates
import-linter's contracts from deptry's manifest comparison.

[DECISION: three packages rather than two. Two cannot express "declared but reaching inside", and
that is the case where the tools genuinely differ — a two-package fixture would make deptry and
import-linter look interchangeable when they are not.]

## The experiments

Each answers a question a docs page cannot, and each produces a number or a verdict, not an
impression.

### 1. What each tool catches on the fixture

Run all three against the fixture and record a matrix: rows are the four bad edges above plus the
one good edge, columns are the tools, cells are caught / missed / **false positive on the good
edge** — the last being the one that disqualifies a candidate for a shipped gate step.

The prediction to test rather than assume: deptry catches the undeclared edge and is blind to the
private-module reach; import-linter catches both but only once someone writes the contract; tach
catches both and needs the most configuration. If that prediction holds, the answer is "deptry for
the manifest question, import-linter for the architecture question, and they are not alternatives".

### 2. Does the undeclared edge actually break a wheel

The ground truth the linters are proxies for, and the one experiment that needs no third-party tool
at all: `uv build --package pkg-worker`, install the resulting wheel into a **clean** venv with no
workspace on the path, and import it. If that fails while `uv sync` at the workspace root succeeds,
the failure mode is real and reproducible, and the number to beat is how early each linter reports
it relative to this.

[DECISION: this experiment runs whatever the tool comparison says. A build-and-import-in-isolation
check is a `test.*` task this repo could own outright — no dependency, no config per consumer, and
it proves the property rather than approximating it. If it is cheap enough, it may be the whole
answer and the linters become optional.]

### 3. Cost, measured on something real

Wall-clock on the fixture is meaningless — every tool is fast on three packages. Run each against a
genuinely large tree instead (this repo's own `.venv/lib/python3.14/site-packages` is 60+
distributions and is right here), and record: cold and warm runtime, whether a cache exists and
where it writes, and the **config authoring burden** — how many lines a consumer must write before
the tool says anything useful. A gate step every consumer inherits has to be inert with no config; a
tool that needs a contracts block per repo cannot be in `quality.check` and would have to be a
standalone task.

### 4. Editable installs, which is where a static tool can quietly lie

uv installs workspace members editable, which on modern uv means an `__editable__` finder or a
`.pth`, not a directory on `sys.path`. Confirm what each tool sees through that: does grimp's
`find_spec` land on the real source (so the graph is complete), or on a shim (so the graph is
silently empty and the contract passes for the wrong reason)? A contract that passes because it
found nothing is worse than no contract, and nothing in the docs of any of these tools addresses it.

[UNVERIFIED: that this is even a hazard — it is a hypothesis from reading `packagefinder.py`, not
something observed. It is first on the list precisely because a false pass is the failure that would
not be noticed.]

## Open questions

[NEEDS CLARIFICATION: does the fixture live in the repo or get generated per run? A committed
`tests/fixtures/monorepo/` is readable and diffable and becomes a second workspace this repo's own
`uv.lock` has to resolve — which is either useful dogfooding or a permanent tax on every `uv lock`
here. Generating it into `tmp_path` costs a builder function and keeps the root lock alone. The
existing `tests/fixtures/sample-service` is the precedent for committing one, and it is also the
reason to hesitate: it is already a member of this repo's workspace.]

[NEEDS CLARIFICATION: if the answer turns out to be "adopt one", does it go in `repo-tasks-quality`
(every consumer resolves it, whether or not they have two packages) or in a new optional extra that
a monorepo consumer opts into? The manifest has never had an optional half, and inventing one for a
single tool is a mechanism this family would then have to maintain. The alternative is that the tool
is a task's dependency rather than the gate's, installed only where the task runs.]

## Recommended direction

Build the fixture first and run experiment 2 against it, because it needs no third-party tool and
its result changes what the others are for: if an isolated build-and-import catches the undeclared
edge cheaply, this repo can own the check and the question becomes whether a linter is worth adding
_on top_ of it. Then run 4, since a false pass would invalidate anything experiment 1 reports about
import-linter. Then 1 and 3.

Re-run `package_health.py` for whichever candidate survives before adopting it — deptry's 172-day
gap and tach's 118-day gap are both the kind of number that resolves in either direction, and the
survey above is a snapshot rather than a fact.

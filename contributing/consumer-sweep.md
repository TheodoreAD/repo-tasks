# Making a change here reach consumers without breaking them

A push to `main` is a deploy. `bootstrap-repo-tasks.sh` is unpinned until a `vX.Y.Z` tag exists
(`selfinstall.stamp` refuses to pin to a tag that isn't real), so every consumer's next CI run
installs whatever `main` is at that moment — with no consumer-side action and no notice.

[PITFALL: a change to the shared tool list or the shipped configs is a breaking change for consumers
even when it is purely additive here. A consumer's `dependency-groups.dev` and its pulled config
files are snapshots taken whenever it was last bootstrapped; the gate that reads them is live.
Additive-here is subtractive-there until that consumer re-runs `ensure-deps` and `configs.pull`.]

This was measured twice in one day (2026-08-24/25), and both times the break was found from the
consumer side, hours later, by reading a red CI run:

- `quality.workflow-check` and its `actionlint-py` manifest entry landed together. Every consumer's
  `dev` group predated the entry, so CI failed with `actionlint: command not found` (exit 127) on
  every push until the next evening.
- `failOnWarnings: true` went into the shipped `pyrightconfig.json`. Every repo `scaffoldapy`
  generates pulls that config at generation time, and the template's own code carried twelve
  warnings — so all ten e2e combinations failed the moment the global tool moved to that commit.

## What counts as a consumer

**A repo that resolves `repo_tasks` at all**, however it does that — not a repo with a particular
file in a particular place.

[PITFALL: **do not define this by a path shape, and do not trust a one-liner that does.** The set
was counted three times in three weeks — two, three, six — and each answer came from a shape
somebody expected: `from repo_tasks` at the top of a `tasks.py`, then a `bootstrap-repo-tasks.sh`.
The 2026-09-10 correction is the sharp case, because the one-liner it prescribed _to stop this
recurring_ is what hid the next two: it cannot see a `tasks/` package, and it cannot see an import
made lazily inside a function, and three of the six are one of those. See
`plans/2026-08-25-consumer-transitions.md`.]

So the list is **declared**, as `[[consumer]]` entries in this repo's `repo-tasks.toml`, and read by
one command:

```shell
inv consumers.diff          # what every declared consumer is behind on — reads only, writes nothing
```

| consumer                 | how it consumes                    | what lags                                       |
| ------------------------ | ---------------------------------- | ----------------------------------------------- |
| `power-user-linux-setup` | pinned in its own `uv.lock`        | task code **and** configs                       |
| `scaffoldapy`            | the global `uv tool` install       | configs only — **plus every repo it generates** |
| `agent-skills`           | the global `uv tool` install       | configs only                                    |
| `ingesta`                | the global `uv tool` install       | configs only                                    |
| `invoke-stubs`           | `repo-tasks` as its own dependency | task code **and** configs                       |

The `*-polite-mcp` repos and `product-research-pipeline` are not consumers — they predate the
template and are its migration backlog, not a sweep target.

**Adding one is an edit to `repo-tasks.toml`; finding one to add is a search plus a reading**, which
is the honest form of the question and is why no command does it. A declared name with no checkout
is reported as `NOT FOUND` rather than skipped, so a stale entry is loud.

[PITFALL: **the reporter measures, it does not sweep.** `consumers.diff` tells you which repos are
behind and on what; acting on that means running that repo's own tasks in its own tree, which is the
per-consumer loop below and a session in that repo. Nothing here writes into a consumer.]

## When to sweep

After changing any of: the `repo-tasks-quality` manifest in `pyproject.toml`, anything under
`src/repo_tasks/configs/`, or a `quality.*` / `test.*` step that shells out to a binary.

`inv consumers.diff` answers **which** of them need it, and it is worth running whether or not you
changed one of those — a consumer can be behind because of somebody else's change, or because
nothing has swept it in weeks. That is not a hypothetical: its first run, 2026-09-13, found
`agent-skills` four config files and two manifest entries behind, in a repo recorded as a consumer
three days earlier whose drift nobody had ever measured.

## The sweep

Once, from anywhere — the tool install is global, not per-repo, so this is not part of the
per-consumer loop:

```shell
inv repo-tasks.update       # move the global uv tool install forward to what you just pushed
```

Then in each consumer's own checkout:

```shell
# Only where this consumer pins repo-tasks in its own uv.lock — and genuinely first, above
# configs.diff, because everything below reads the installed package (see the pitfall below).
inv deps.lock --package repo-tasks
inv venv.sync               # or plain `uv sync` where the consumer publishes no `venv` collection

repo-tasks configs.diff     # what this consumer has drifted from — both configs and dev group
repo-tasks configs.ensure-deps
inv deps.lock               # re-resolve uv.lock; review the diff
inv venv.sync
inv configs.pull
inv quality.precommit       # the gate, against the new tool and the new configs
```

`configs.diff` is first _of the reading steps_ for a reason: it reports both halves of the drift
(stale config files _and_ `dependency-groups.dev` entries the manifest has grown), so it tells you
which of the four steps between it and the gate this particular consumer actually needs — often
none, when the change was to task code rather than to the manifest or the shipped configs. Run the
gate regardless; that is what says the new tool works here. `ensure-deps` is additive and idempotent
— it never touches an entry already present — so running it when nothing is missing costs nothing.

One consumer is also a `repo-tasks-quality` entry (`invoke-stubs`), and since 2026-09-13 both
`configs.diff` and `ensure-deps` skip the entry naming the project they are running in, printing
why. Nothing to do by hand there any more — but a consumer still running an older `repo-tasks` will
be told to splice that package into its own dev group, so if the skip line is absent, the pin bump
above has not landed yet and that one next step must be ignored.

In `scaffoldapy`, `inv quality.precommit` is only half the sweep: finish with `inv test.integration`
(~80s), which renders every combination and runs the _generated_ repo's own gate. See the two-gates
pitfall below.

One-time per consumer, and the easiest thing in this file to miss because nothing anywhere reports
it: a consumer that hand-builds its own root `Collection` instead of importing `ns` needs
`runner.configure(namespace)` in its `tasks.py`, or report mode does nothing there however the
environment is set — [`quality-gate.md`](quality-gate.md), "Turning it on in a consumer".
`rg -n 'runner.configure' tasks/` answers it in one call.

**Where a consumer regenerates anything from the live namespace, the bump and the regeneration are
one commit.** The gate already does the regenerating — `docs.generate` is the first step of `fix`,
so `inv quality.precommit` above rewrites those blocks as part of the sweep — and the only decision
left is how the result is committed. `rg -n '^\[docs\]' repo-tasks.toml` says whether this consumer
has any; two of the four repos in the family do.

[PITFALL: **splitting them makes the pin commit fail its own tests, and the failure names the wrong
cause.** Hit 2026-09-10 sweeping the lock-pinning consumer: it renders a task index from the live
namespace, `v0.3.0` had reworded a `configs.diff` docstring, and its `test_catalog` therefore failed
on the commit that touched nothing but `uv.lock`. A test failing on a lock-only commit reads as a
broken bump — the one explanation that sends you to re-resolve a dependency that is fine. The sweep
cannot be split into separately-gated commits at all in such a repo, and that is a property of the
repo rather than a mistake in the split.]

[PITFALL: **`ensure-deps` will not update an entry the consumer already declares, so a manifest
_constraint_ is a hand edit.** It is additive by contract — never touches an entry already present —
which is what makes it safe to run at any time, and that same property means a `hadolint-py` that
grew `!=2.15.1.2` in the manifest stays a bare `hadolint-py` in every consumer that already had one.
Until 2026-09-06 nothing reported this either, because both `configs.diff` and `ensure-deps`
compared by bare name; `configs.diff` now names each such entry and the exact edit. Do those edits
in the sweep, before `deps.lock`, or the re-lock resolves the version the constraint exists to
exclude.]

[PITFALL: `configs.pull` prints "pulled" for every file whether or not it wrote anything. Seen live
2026-08-25: a consumer's installed `repo_tasks` was still the pre-change commit, so the first pull
"pulled" the old config unchanged and looked successful. `inv repo-tasks.update` genuinely first,
and `configs.diff` to confirm, or the sweep silently does nothing.]

[PITFALL: `inv repo-tasks.update` is not enough for a consumer that pins `repo-tasks` in its **own**
`uv.lock` — `power-user-linux-setup` does, `scaffoldapy` does not. There, `inv` resolves
`repo_tasks` out of that repo's `.venv`, not out of the global tool, so the pull writes the old
configs while reporting success in exactly the shape above. Hit again 2026-08-27, one day after the
pitfall it repeats. `uv lock --upgrade-package repo-tasks` and re-sync before pulling;
`configs.diff` listing a file you know changed is the tell.

**Its worse form is a `configs.diff` that reads clean, and that is why the bump is in the command
list above rather than only here.** Hit 2026-09-05 sweeping that consumer: with `diff` run first, it
reports drift against the _old_ shipped configs, `pull` then writes those, and a second `diff` after
the bump reports the same thing — an identical report on both sides of the bump, which reads as "the
bump changed nothing" rather than as "nothing has been measured yet".]

## What the sweep actually costs

It is not a config refresh. Measured 2026-08-27, sweeping one release that added three tools:

- Three of the four new gate steps found **real defects in both consumers** — 12 zizmor findings in
  `power-user-linux-setup`, 2 more in `scaffoldapy` and its template, and 16 ruff `PT`/`FURB` hits.
  Budget for fixing them, not just for running the commands.
- The consumer's own suite can go red on the **shipped `pytest.ini`**, not on any new tool: `error`
  as a warning filter turned copier's `DirtyLocalWarning` into 21 failures in `scaffoldapy` and
  starlette's `TestClient` deprecation into a collection error in every generated web service. Both
  fixes belong in the consumer (a scoped `catch_warnings`, a dependency migration) — never in the
  shipped file, whose "ignores go in the shared copy" decision
  ([`quality-gate.md`](quality-gate.md)) assumed a family-uniform dependency set that a consumer's
  own dependencies break.
- `scaffoldapy`'s e2e is the only thing that tests the generator's output, and it earned that
  billing: it found a defect in **repo-tasks itself** (`untested-modules` demanding a `test_init.py`
  for a docstring-only `__init__.py`, which every generated repo has). Fixing it meant a second push
  here and a second `inv repo-tasks.update` mid-sweep. Expect that round trip.

[PITFALL: a green consumer gate on this machine is not a green CI run there, and
`filterwarnings =
error` is where the two come apart. The runner's checkout differs from a working
tree in ways the consumer's own tests can see — `actions/checkout` clones at depth 1, and CI's tree
is never dirty. `scaffoldapy` hit exactly that: locally copier raised `DirtyLocalWarning` (full
clone, uncommitted template edit), in CI it raised `ShallowCloneWarning` (clean, depth 1), and each
condition raises only its own half. Fixing the one the sweep saw left CI red on the other. Reproduce
with `git clone --depth 1 file://<path>` before calling a consumer done.]

## Two lags, both invisible from a green terminal

- **The dev machine lags `main`.** The global `uv tool install` is whatever `inv repo-tasks.update`
  last fetched. A local gate can pass for a day against the old tool while CI runs the new one.
- **A user-wide binary masks a missing group entry.** `power-user-linux-setup` installs
  `actionlint`, `shfmt`, and friends onto `PATH` machine-wide, so a consumer whose `dev` group never
  declared them still passes locally and fails in CI, where only the group exists. This is what
  `require_tool`'s preflight message is worded for: it names the manifest entry, because the binary
  being on `PATH` is not evidence the group declares it.

[PITFALL: `scaffoldapy` is two things — a repo with its own gate, and a generator whose output has
its own gate. `inv quality.precommit` there is evidence about the first only. Only its e2e tier
(`inv test.integration`, ~80s, renders every combination and runs the generated `inv quality.check`)
tests the second, and it is the only thing in the family that does. Any "consumers verified" claim
has to name which of the two it ran, and against which repo-tasks commit — its e2e is evidence about
the global tool it rendered with (`inv repo-tasks.version`), not about `main`.]

## Still open

Whether `scaffoldapy`'s e2e becomes a pre-merge canary here (locally, or as a cross-repo CI job
bootstrapping repo-tasks from the PR's ref), and whether tagging a release — which would pin
consumers and turn each of these into a deliberate per-consumer update — is the better answer than
any of the above. Both in `plans/2026-08-25-consumer-transitions.md`.

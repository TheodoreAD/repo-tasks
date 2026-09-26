# Making a change here reach consumers without breaking them

A push to `main` is a deploy to any consumer whose `bootstrap-repo-tasks.sh` still carries the
unpinned form: its next CI run installs whatever `main` is at that moment, with no consumer-side
action and no notice.

[PITFALL: **that used to be "unpinned until a `vX.Y.Z` tag exists", and the tag stopped being the
variable on 2026-09-04.** `selfinstall.stamp` does refuse to pin to a tag that isn't real, so the
sentence was true when written and became a false explanation the moment `v0.2.0` was cut — the
script stays unpinned until somebody re-runs `stamp` **in that consumer**, which is a per-repo
action nothing prompts. It read as a property of this repo's release state for three weeks, which is
why the stamp step is now in the sweep rather than implied by tagging.]

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
made lazily inside a function, and three of the six are one of those.]

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

[DECISION: **declared rather than derived, because a derived list fails silently and a declared one
fails loudly.** Settled 2026-09-13 with the reporter. A reporter that derives its own list inherits
whatever shape the derivation encodes, and a reporter that misses a consumer reports success — the
exact defect it was built to catch, in its worst form. Declared, a consumer nobody added is
**absent** from the report rather than silently excluded from a green one. The search keeps the job
it always had, which is how a human finds a consumer to add.

Only the names are in version control. Where the checkouts live is machine-local and comes from
`$REPO_TASKS_PROJECTS_ROOT`, defaulting to this repo's parent directory — see
`projects.projects_root` for why that split is the right one.]

[PITFALL: **the first count was right, and still went stale in two days.** Two consumers on
2026-08-25 was a correct measurement; `agent-skills` gained its `tasks.py` on 2026-08-27. That is a
different failure from a wrong method, with a different fix: a better method does not help a correct
answer nobody re-ran, and only something that runs does. The reporter is the re-running.]

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

**First, a release, whenever what the sweep is for is not tagged yet.** Check with
`git log --oneline <latest tag>..main -- src/`: anything listed there reaches no consumer, because
both the update below and the stamp at the end work from tags.

Then once, from anywhere — the tool install is global, not per-repo, so this is not part of the
per-consumer loop:

```shell
inv repo-tasks.update       # move the global uv tool install forward to the latest *tag*
```

[PITFALL: **`update` installs the latest release, not what you just pushed.** Measured 2026-09-26:
`v0.3.0` was the latest tag while seventeen source commits sat on `main` after it, including the fix
for `ensure-deps` corrupting a `"pkg[extra]"` dev group and the self-reference skip for
`invoke-stubs`. Every sweep then would have run the tool with both bugs, and its closing `stamp`
would have pinned that consumer's CI to it. This file's own advice for both bugs was "`update`
first", which was no advice at all until a tag carried the fixes. The comment on that line used to
say "to what you just pushed", which is where the misreading came from.]

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
inv repo-tasks.stamp        # re-pin this consumer's bootstrap to the version its gate just passed
```

**The stamp is last, and it is what actually pins a consumer.** `inv repo-tasks.update` moves the
_developer machine_ to the latest tag; a consumer's CI installs whatever its
`bootstrap-repo-tasks.sh` says, and until 2026-09-26 all three consumers carrying that script still
had the unpinned form, so their CI tracked `main` while their developers were on `v0.3.0` — local
green saying nothing about CI, which is the failure this whole file exists for.

[DECISION: **pin, rather than keep consumers' CI on `main`. Settled 2026-09-26.** It was answerable
then and not in August because of the canary. Pinning defends against "a push here breaks a
consumer", and until 2026-09-13 the only detector for that was those consumers' own unpinned CI
going red _after_ the push — pinning would have removed the family's only check and put nothing in
its place. `canary.yml` now supplies the pre-push half for `scaffoldapy`, whose generated output is
the expensive case, so the unpinned CI stopped being load-bearing.

The cost is that a task-code fix here stops reaching those consumers' CI for free. `3a58b1d` and
`7fc0b23` both landed in `scaffoldapy` the moment the global tool moved; after pinning, a fix needs
a tag here, a re-stamp there, and a commit. That converts invisible breakage into visible staleness,
which is the right way round: `consumers.diff` reports staleness, and nothing reports breakage until
CI is red.]

It runs after the gate because `stamp` pins the version **active in the process running it**, not
the newest tag: that records what this repo was verified against, and running it earlier would pin a
version not yet known to work here. It needs the network for the tag list, and falls back to the
unpinned form rather than pinning a tag that does not exist. `power-user-linux-setup` and
`invoke-stubs` have no bootstrap script — they pin through their own lock, so the step is a no-op
there and the `inv deps.lock --package repo-tasks` at the top is their equivalent.

[PITFALL: **not `inv configure`.** That is the fresh-checkout composite — dev-env setup,
`configs.pull` and `stamp` in one — so in a sweep it re-runs steps already done above, in a
different order. `stamp`'s own docstring used to send you there, citing the generated script's
header for why a human "shouldn't run it directly"; that header warns against re-running **the
script**, which yanks the global tool out from under every other repo, and says nothing against
running the task. Corrected 2026-09-26, in the same change that made the step part of this sweep —
but a consumer on an older `repo-tasks` still has the old wording.]

`configs.diff` is first _of the reading steps_ for a reason: it reports both halves of the drift
(stale config files _and_ `dependency-groups.dev` entries the manifest has grown), so it tells you
which of the four steps between it and the gate this particular consumer actually needs — often
none, when the change was to task code rather than to the manifest or the shipped configs. Run the
gate regardless; that is what says the new tool works here. `ensure-deps` is additive and idempotent
— it never touches an entry already present — so running it when nothing is missing costs nothing.

One consumer is also a `repo-tasks-quality` entry (`invoke-stubs`), and since 2026-09-13 both
`configs.diff` and `ensure-deps` skip the entry naming the project they are running in, printing
why. Nothing to do by hand there any more — but a consumer still running an older `repo-tasks` will
be told to splice that package into its own dev group. `v0.3.0` is such a version; the skip shipped
in `v0.4.0`. So if the skip line is absent, the tool is older than the skip, and that one next step
must be ignored.

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

[PITFALL: **`ensure-deps` used to corrupt a consumer whose `dev` group names an extra, and an older
`repo-tasks` still will.** Its array regex stopped at the first `]`, which in `"pkg[extra]"` is
inside the string, so it read the group as declaring nothing, reported every manifest entry as
added, and spliced all of them into the middle of that string — leaving a `pyproject.toml` that no
longer parsed as TOML. Hit live in `ingesta` on 2026-09-13, where only `uv lock --check` stood
between that and a commit. **Fixed 2026-09-26**: membership now comes from tomllib, the same reader
`configs.diff` always used, and the write offsets from a scan that skips strings and comments.

Kept because the sweep runs whatever tool the consumer has, not this working tree. The tell is the
two commands disagreeing in one run — `diff` naming two missing entries while `ensure-deps` prints
"added" for all of them — and if you see it, the global tool predates the fix. The fix shipped in
`v0.4.0`, 2026-09-26, so `inv repo-tasks.update` reaches it from that tag on. A file already
corrupted by it now gets a sentence naming this cause from both commands, instead of a
`TOMLDecodeError` traceback.]

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
- **Where the sweep starts by raising that consumer's floor, budget for a lint red rather than a
  type-check red.** The shipped `ruff.toml` carries no `target-version` and reads the floor from
  `requires-python`, so the edit that settles the floor question also turns on the syntax-upgrade
  rules at the new floor: `ingesta` raising `>=3.11` to `>=3.14` on 2026-09-13 took two `UP047` hits
  on generics still written with a `TypeVar`, a `UP043`, and a formatter change dropping the
  parentheses from a multi-exception `except`. The derived `pythonVersion` that everyone expects to
  fail never got the chance — the floor moved up to meet the code instead.

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

## One consumer is checked on every push here

`.github/workflows/canary.yml` runs `scaffoldapy`'s e2e tier against a global `repo-tasks` installed
from the ref being pushed, so the half of the sweep that tests **what gets generated** happens
without anyone deciding to run it. Its design and the two ways to misread it are in
[`quality-gate.md`](quality-gate.md), "The consumer canary runs as its own workflow too".

[PITFALL: **it replaces no step in this file.** One consumer of five, and of that one only the
generated-repo half — it never pulls a config, never touches a dev group, and knows nothing about
the four consumers whose snapshots have drifted. A green canary beside four consumers behind is the
normal state.]

## Still open

Nothing about whether to pin: that is the decision beside the stamp step above.

Nor about which consumers are unpinned, nor which lack the security-workflow caller:
`consumers.diff` reports both since 2026-09-26 — `bootstrap unpinned` or a pin behind the version
the run measured with, and a missing caller or one whose SHA is behind the reusable workflow it
names. Report-mode wiring was the third candidate for a check and needed none: it only bites a
consumer that hand-builds its own root `Collection`, which is `power-user-linux-setup` (wired) and
the repos `scaffoldapy` generates (that repo's own open question).

What stays open is the part of a sweep that is a **reading** rather than a check. No command can do
these, and a sweep that skips them reports success:

- **Whether a derived value is right.** `configs.pull` writes `pythonVersion` and `anyio_mode` per
  consumer, so byte-identical across the family is not the test; that the derived version matches
  what that repo declares, and that its type check still passes there, is.
- **The packaged-`tests/` decision.** `configs.pull` writes both config halves but cannot decide
  whether that repo wants the `__init__.py` files — [`type-checking.md`](type-checking.md), "Why
  `tests/` is a package", which says the decision stays deliberate.
- **Whether to `venv.recreate` onto the declared floor.** `venv.check` reports a mismatch in nearly
  every consumer on first run; whether to develop on the floor rather than the newest is that repo's
  call.
- **Task-code lag in a consumer pinning `repo-tasks` in its own lock** (`power-user-linux-setup`,
  `invoke-stubs`), which no diff of config files can see.
- **Whether a consumer has CI at all.** `invoke-stubs` has no `.github/`, so its local gate is the
  whole of the evidence for a sweep there, and the security caller cannot be added until that repo
  decides whether it wants CI.

[PITFALL: **both new checks landed by finding something in a repo that looked finished.** The pin
check named `ingesta`, swept and reported up to date hours earlier; the caller check named
`power-user-linux-setup`, the most-swept consumer in the family and clean on every other line.
Neither had been missed by a sweep — both items were on the complement list, which is exactly the
list no command read. So "swept recently" is not evidence about anything a sweep does not measure,
and the list of readings above is where to look for what that is.

It is the same finding a fourth time. Membership known, drift unmeasured (`agent-skills`); a list of
repos derived for three weeks that nothing then measured; a canary that already existed wired to the
wrong event; a pin at a known path nobody read. Each time the missing thing was **something that
runs**, and each time the work that felt like progress was refining a description instead.]

---
status: in-progress
updated: 2026-09-13
depends_on: [scaffoldapy, power-user-linux-setup]
---

# Making a change to the shared tool list or shipped configs reach consumers without breaking them

## Context

Two changes here on 2026-08-24/25 broke every consumer's CI, and each was found from the consumer
side, by reading a red run, hours later:

1. `afe1bcf` added `quality.workflow-check` (`actionlint`) to `quality.check`; `5c5ab92` added
   `actionlint-py`/`act-bin` to `repo-tasks-quality`. `scaffoldapy`'s CI failed with
   `actionlint: command not found` (exit 127) on every push from 19:38Z until fixed the next evening
   — its `dev` group had been populated by `configs.ensure-deps` before the list grew, and nothing
   re-runs `ensure-deps` after generation.
2. `09321ae` flipped `failOnWarnings` on in the shipped `pyrightconfig.json`. Every repo
   `scaffoldapy` generates pulls that config at generation, and the template's own code carried
   twelve warnings across four files — so all ten e2e combinations failed the moment the global tool
   moved to that commit. The now-retired `plans/2026-08-25-type-check-warning-noise.md` (settled
   content in `contributing/type-checking.md`) had recorded "scaffoldapy is unaffected (verified)",
   which was true of scaffoldapy's own tree and false of what it generates.

Both were the same mechanism, seen twice in a day. What made each expensive:

- **Consumers track `main`, immediately and silently.** `bootstrap-repo-tasks.sh` is unpinned until
  a `vX.Y.Z` tag exists (`selfinstall.stamp` refuses to pin to a tag that isn't real), so a
  consumer's CI installs whatever `main` is at run time. A push here is a deploy to every consumer's
  next CI run, with no consumer-side action and no notice.
- **The dev machine lags `main`, so local green means nothing about CI.** The global
  `uv tool install` is whatever `inv repo-tasks.update` last fetched. In `scaffoldapy` the local
  gate passed for a day with the old tool while CI ran the new one; then, once updated, the gate
  still passed locally because `actionlint` was on `PATH` user-wide from `power-user-linux-setup`,
  masking the missing group entry. Two different lags, both invisible from a green terminal.
- **`configs.ensure-deps` is one-shot.** Additive and idempotent, but nothing runs it after the
  first time, and nothing reports that a consumer's `dev` group has fallen behind the manifest the
  gate now assumes. A gate step that shells out to a tool the consumer never declared fails with
  exit 127 and no hint.
- **"Verified against consumers" checked the wrong artifact.** `scaffoldapy` is two things: a repo
  with its own gate, and a generator whose output has its own gate. Only its e2e tier
  (`inv test.integration`, ~80s, renders every combination and runs the generated
  `inv quality.check`) tests the second, and it is the only thing in the family that does.

[PITFALL: a family-wide config or tool-list change is a breaking change for consumers even when it
is additive here. The consumer's `dev` group and pulled configs are snapshots; the gate that reads
them is live. Additive-here is subtractive-there until the consumer re-runs `ensure-deps` and
`configs.pull`.]

[PITFALL: `scaffoldapy`'s own `inv quality.precommit` is not evidence about generated repos, and its
e2e is only evidence about the global tool it rendered with (`inv repo-tasks.version`), not about
`main`. Any "consumers verified" claim here has to name which of the two it ran and against which
repo-tasks commit.]

## Open questions

- [DECISION: yes, every gate step preflights its binary — `configs.require_tool`, landed `99f26a8`.
  The "every tool-running task would need it" objection held and was paid: eight call sites across
  `quality.py` plus `testing._pytest`. It lives in `configs.py` because that module already owns the
  `repo-tasks-quality` manifest and is the only place both `quality.py` and `testing.py` can import
  from without a cycle (`quality` already imports `testing`). In the file-gated steps the call sits
  _inside_ the `if files:` branch — hoisting it would turn "this repo has no shell scripts" into a
  hard failure and cost those steps the no-op contract their docstrings promise. Resolved
  2026-08-26.]
- [DECISION: `configs.diff` reports dev-group drift alongside config-file drift, landed `e169837`.
  Not `repo-tasks.status`: that task compares the installed tool version against the repo's stamp, a
  different question, and `diff` is already the drift command. The dev group is read with tomllib
  rather than `ensure_deps`' `_DEV_ARRAY_RE` — that regex sees repo-tasks' own
  `dev = [{ include-group = "repo-tasks-quality" }]` as declaring nothing and would report the whole
  manifest missing in the repo that owns it. Resolved 2026-08-26.]
- [NEEDS CLARIFICATION: is the fix pinning, or a release cadence? The moment a `v0.1.0` tag exists,
  `stamp` pins consumers to it and `repo-tasks.update` targets tags — the machinery is built
  (`contributing/release-flow.md`) and unused. Pinned consumers stop tracking `main`, which turns
  each of these incidents into a deliberate per-consumer update. The cost is that a fix here reaches
  nobody until released, and every consumer has to be walked forward — which is the "consumer sweep"
  below either way.]
- [NEEDS CLARIFICATION: what is the consumer sweep, concretely? When `repo-tasks-quality` or a
  shipped config changes, which repos need `inv repo-tasks.update` + `configs.ensure-deps` +
  `deps.lock` + `configs.pull` + gate, and where is that list? Measured 2026-08-25 across
  `~/projects/github.com-personal`: exactly two consumers exist — `power-user-linux-setup` (swept by
  hand, `395dc3d`) and `scaffoldapy` (swept by hand, `56d80e8`, plus template fixes `2e29f2b`). The
  five `*-polite-mcp` repos and `product-research-pipeline` do not consume repo-tasks at all (no
  `from repo_tasks` in any `tasks.py`, no `bootstrap-repo-tasks.sh`, no workflow running the gate) —
  they predate the template and are its migration backlog, not a sweep target. The list is small
  enough today that a checklist in `contributing/` is the whole mechanism; a task that runs the
  sweep against local checkouts earns its keep only once those repos are regenerated onto the
  template. Written down in `contributing/consumer-sweep.md`, landed `d47b37a`; resolved 2026-08-26.
  Whether it becomes a task stays open, on the condition stated above.]
- [NEEDS CLARIFICATION: should `scaffoldapy`'s e2e be this repo's canary — run before merging a
  change to `repo-tasks-quality`, `configs/`, or any `quality.*` composite? Locally that is
  `inv repo-tasks.update` from this checkout (or a `uv tool install` of the working tree) followed
  by `inv test.integration` in `scaffoldapy`. In CI it would be a cross-repo job: check out
  `scaffoldapy`, bootstrap repo-tasks from the PR's ref instead of `main`, run its integration tier.
  ~2 min, and it would have caught both incidents before merge.]

## Recommended direction

Rough, in order of payoff per effort:

1. ~~Preflight-with-fix in the gate steps that shell out to a group-installed tool~~ — landed
   2026-08-26, `99f26a8`.
2. ~~Dev-group drift in `configs.diff`~~ — landed 2026-08-26, `e169837`.
3. ~~Write the consumer sweep down in `contributing/`~~ — landed 2026-08-26, `d47b37a`. Whether it
   becomes a task is still open.
4. The `scaffoldapy` canary as a CI job here — the only item that catches a break _before_ it ships.
5. Tagging a release is a policy decision that changes what all of the above defends against; take
   it when the release flow is exercised for real, not as part of this plan.

## Verification (2026-08-26)

1–3 were exercised against a real scratch consumer, not only through `MockContext`:

- Config files byte-identical, dev group short of `actionlint-py` and friends: `configs.diff` exits
  1 with `dependency-groups.dev is missing: ...` and only the ensure-deps/lock/sync steps — the
  incident's exact shape, which previously printed "up to date".
- `inv quality.type-check` with `basedpyright` off `PATH`: the preflight message naming
  `basedpyright` and the three commands, instead of exit 127.
- `inv quality.shell-check quality.workflow-check` with `shellcheck`/`actionlint` off `PATH` in a
  repo with neither file kind: exit 0, silent — the no-op contract survives the preflight.
- `inv quality.precommit` here: 0 errors, 0 warnings, 294 unit tests.

Both consumers were then swept for real, against the global tool moved to `68c56bf` (this repo's
`main`), which makes the run below evidence about `main` and not only about whatever the machine
happened to have installed:

| repo                     | `configs.diff` | own gate                        | generated repos |
| ------------------------ | -------------- | ------------------------------- | --------------- |
| `power-user-linux-setup` | up to date     | 0 errors, 0 warnings, 353 tests | n/a             |
| `scaffoldapy`            | up to date     | 0 errors, 0 warnings, 27 tests  | 10/10 e2e, 78s  |

Neither had drifted and neither working tree changed — expected, since these three commits touched
task code rather than the manifest or the shipped configs, so there was nothing to re-snapshot. What
the sweep establishes is the other direction: the preflight and the widened `diff` do not break
either consumer, including the ten generated repos that are the only thing testing scaffoldapy's
second gate.

Walking it also corrected the sweep doc: `inv repo-tasks.update` is a single global step, not part
of the per-consumer loop, and `scaffoldapy`'s sweep is not finished at `quality.precommit` —
`test.integration` is the half that covers what it generates.

[UNVERIFIED: the preflight has still never fired from a consumer's own CI, only locally — no
consumer has yet had a dev group behind the manifest since it landed. The first family-wide manifest
change after this is the real test.]

## The first unswept manifest change (2026-08-28)

`ae54087` added `pytest-socket` and `pytest-cov` to `repo-tasks-quality`, and the consumer sweep for
it was **deliberately declined** — the session pushed and stopped, at the user's choice. So as of
`863ede6` both consumers sit behind the manifest for the first time since the preflight landed,
which is exactly the condition the `[UNVERIFIED:]` above is waiting on. Measured here rather than
left implicit:

| repo                     | `pytest-cov` | `pytest-socket` | shipped `pytest.ini` ignore line |
| ------------------------ | ------------ | --------------- | -------------------------------- |
| `power-user-linux-setup` | present      | **missing**     | **absent**                       |
| `scaffoldapy`            | present      | **missing**     | **absent**                       |

The prediction this makes is falsifiable, and worth checking rather than assuming, because it is the
_opposite_ outcome to the incident that created this plan: neither plugin is a binary any gate step
shells out to — `_GATE_TOOL_DISTRIBUTIONS` does not list them, and `pytest-socket` does nothing
until a conftest calls `disable_socket()`. So `configs.diff` should exit 1 naming the missing entry
while **both consumers' CI stays green**, where `actionlint` produced exit 127 on every push. If a
consumer does go red on this, the inert-by-default reasoning in
[`2026-08-27-pytest-plugin-survey.md`](2026-08-27-pytest-plugin-survey.md) is wrong and that plan's
selection criterion needs revisiting, not just this sweep.

[DEFERRED: run the sweep and record which way it went. Until then the drift is known and benign, not
forgotten — that distinction is the whole reason this section exists rather than a memory entry.
**Answered for `power-user-linux-setup` 2026-09-05** and recorded at the end of this file: the
prediction held, and `pytest-timeout` turned out to be missing from that consumer's group too.
`scaffoldapy` is still unswept.]

## The second unswept change (2026-08-29) — the sweep is now batched

`8f384d7` added `ignore:unclosed file:ResourceWarning` to the shipped `pytest.ini` (that file's own
comment has why, in full — invoke's `Local` runner never closes its subprocess pipes). The sweep was
deferred again, deliberately and at the user's direction: more work is landing here first, and one
sweep covering everything accumulated is cheaper than one per change.

So the pending consumer transition is now **two items, not one**, and they are different kinds:

| change    | what drifts                                       | detected by                                 |
| --------- | ------------------------------------------------- | ------------------------------------------- |
| `ae54087` | `dependency-groups.dev` short of `pytest-socket`  | `configs.diff` (dev-group drift, `e169837`) |
| `8f384d7` | `pytest.ini` byte-different from the shipped copy | `configs.diff` (config drift, original)     |

That is worth stating because it makes the sweep a better test than either change alone: the two
halves of `configs.diff` — the config-file comparison it always had, and the dev-group comparison
added in `e169837` — should now both fire on the same run, against both consumers. Neither had ever
fired together before.

The prediction from the section above is unchanged and now covers both: `configs.diff` exits 1
naming each, and **both consumers' CI stays green**, because neither change touches a binary a gate
step shells out to. `pytest.ini`'s new line is inert in a repo whose tests never leak a file handle,
and strictly loosening in one whose tests do.

[PITFALL: neither item reaches a consumer until this repo's commits are pushed _and_ the global tool
is moved — `configs.pull` reads the installed `repo_tasks` package by default, and
`inv repo-tasks.update` is the single global step that moves it (not a per-consumer one; the
2026-08-26 walk-through corrected the sweep doc on exactly this). A sweep run before that step
measures the old package and reports "up to date" for changes that have not shipped, which looks
identical to a clean sweep.]

[DEFERRED: one batched sweep once the current run of work here is done. **Half done** — the
`power-user-linux-setup` half ran 2026-09-05 and every prediction below is answered for it in "The
batched sweep's first half ran" at the end of this file; `scaffoldapy` still owes its half, and it
is the half that matters most, since its e2e tier is the only thing testing what it generates.
Record which way each prediction went — the `[UNVERIFIED:]` above is still waiting on a preflight
that has never fired from a consumer's own CI, and none of the changes below will make it fire,
since none is a gate binary.

**Read the list below as history rather than as scope, since 2026-09-13.** The measurement at the
end of this file settled that `configs.diff` against the installed tool **is** the list for anything
it can see — every shipped config file, every manifest entry — and that a hand-kept list is wrong
about those by construction rather than by neglect. What is still scope is the complement: the items
no diff can report, because they are not a file it compares or an entry it reads.

The complement, in full:

- **Report-mode wiring.** `rg -n 'runner.configure' tasks/` — a consumer building its own root
  `Collection` needs the call, and without it produces output byte-identical to a wired consumer
  with the variable unset, so there is nothing to read it off.
- **The security-workflow caller.** An addition to a consumer rather than a `configs.pull`, so
  nothing compares it. `scaffoldapy` has since landed one and its template ships one to every repo
  it generates (measured 2026-09-13); `agent-skills`, `ingesta` and `invoke-stubs` have none.
- **The packaged-`tests/` `__init__.py` decision.** `configs.pull` writes both config halves; it
  cannot decide whether that repo wants the files, and the plan that owns this says the decision
  must stay deliberate rather than implied by the pull.
- **`venv.check` / `venv.recreate`.** A per-repo judgement about developing on the declared floor
  rather than the newest interpreter. No diff has an opinion about it, and it will report a mismatch
  in every consumer on first run.
- **Whether a derived value is _right_.** `configs.pull` now writes `pythonVersion` and `anyio_mode`
  per consumer, so "byte-identical across the family" stopped being the test; that the derived
  version matches what that repo declares, and that its type check still passes there, is a reading.
- **Task-code lag in a consumer that pins `repo-tasks` in its own lock** — invisible to any diff of
  config files. Two consumers: `power-user-linux-setup` and `invoke-stubs`.

Everything below is kept for its reasoning — what each change was for and what it predicted, with
several bullets withdrawn in place — and none of it is a checklist to work through:

- `ae54087` — `pytest-socket`/`pytest-cov` added to the `repo-tasks-quality` manifest.
- `8f384d7` — `ignore:unclosed file:ResourceWarning` in the shipped `pytest.ini`.
- The two `ci` tasks added since: status annotations, and `check-actions`.
- `actions/checkout@v4` → `v7` across the consumers, plus `setup-python` and two `artipacked`
  suppressions to retest in `power-user-linux-setup`.
- `3a58b1d` — `docs.link-check` no longer reads inline code as a link. Consumer-visible for the same
  reason as the rest: consumers run this task out of the installed package, and any consumer whose
  markdown documents PEP 695 generics is currently red on correct input. This one is a _fix_ to a
  gate a consumer already runs, so unlike the others it changes an outcome rather than a
  configuration — a consumer's CI could go from red to green on the sweep, which is the one way a
  prediction of "both CIs stay green" could be right for the wrong reason.
- `7fc0b23` (2026-09-04) — `docs.link-check` now resolves a link's **fragment** against the target's
  real headings, across every tracked `.md`. Same task as the item above and the opposite risk: that
  one could only turn a consumer red-to-green, this one is strictly _stricter_ and can turn a green
  consumer **red on links nothing has ever checked**. It is a gate step, so a consumer meets it on
  its first `quality.check` after the bump with no config change of its own. **Measured 2026-09-08
  and the risk is empty in fact** — both consumers report no broken links under the new check, and
  `scaffoldapy` was never behind on it at all, since it takes the task code from the global tool.
  See "The anchor-check prediction, falsified" below; the sequencing this item originally asked for
  is withdrawn.
- `487c9c8` (2026-09-08) — `ignore:The anyio.abc.BlockingPortal alias is deprecated` in the shipped
  `pytest.ini`. The first entry in that file meant to be **deleted** again, and the only sweep item
  that fixes a consumer rather than moving it: a repo whose tests import `fastapi.testclient`
  currently cannot collect at all under the shipped `filterwarnings = error`.
  [`2026-09-07-starlette-anyio-deprecation-breaks-web-consumers.md`](2026-09-07-starlette-anyio-deprecation-breaks-web-consumers.md)
  owns it and its `[UNVERIFIED:]` is discharged by exactly this sweep reaching `scaffoldapy` — that
  repo's `web_service` e2e combination is the original repro, and it needs this pushed and
  `inv repo-tasks.update` run there before it can go green.
- `949607c` — `target-version` deleted from the shipped `ruff.toml`. The sweep's own `configs.pull`
  will rewrite each consumer's copy, after which that consumer's `requires-python` decides its ruff
  floor. Check the field exists in each before pulling: a consumer without it moves from a 3.11
  linter to an unversioned one and a 3.10 formatter, which is the one regression this change can
  cause and the one `configs.diff` will not show.
- `c514bd9` — `configs.pull` now derives two lines per consumer: `pythonVersion` in
  `pyrightconfig.json` from that repo's `requires-python`, and `anyio_mode` in `pytest.ini` from
  whether its lock resolves AnyIO. Unlike everything else in this list, the sweep's own `pull` is
  what makes each consumer correct, and each ends up with a _different_ file — so "byte-identical
  across the family" stops being the thing to check. What to check instead, per consumer: that the
  derived `pythonVersion` matches what that repo actually declares, and that its type check still
  passes at that version rather than at the venv's. **The type checker moving from the developer's
  interpreter to the declared floor is the one change here that can turn a green consumer red on
  correct input** — anything using syntax above its own declared floor has been passing only because
  nothing was checking. That is the finding, not a regression, but it is the reason this item wants
  running first and alone.
- `b79b76a` — `quality.type-check --python-version`. Additive and unused by default; nothing to
  check beyond it being present.
- `de596ce` — `venv.check` and `venv.recreate`. Additive: nothing runs either on a consumer's
  behalf, and `venv.create` still lets uv choose. Expect `venv.check` to report a mismatch in
  **every** consumer on its first run, because uv has always built each venv with the newest
  interpreter satisfying that repo's floor — that is the pre-existing state being made visible, not
  something the sweep broke. Whether to `venv.recreate` each one is a per-repo call: it is what
  makes local test runs agree with the `pythonVersion` the same sweep derives into
  `pyrightconfig.json`, and this repo's own gate passes whole on 3.11, but it also means developing
  on the floor rather than the newest.
- The packaged-`tests/` pair, 2026-09-04: `extraPaths: ["."]` in the shipped `pyrightconfig.json`
  and the `flake8-tidy-imports` `banned-api` entry for `src` in the shipped `ruff.toml`. Moved here
  from the now-retired `plans/2026-08-30-tests-import-layout.md`, which owned the decision; the
  reasoning is in [`../contributing/type-checking.md`](../contributing/type-checking.md), "Why
  `tests/` is a package". **There is no ordering hazard and this item wants no sequencing** — a
  consumer that pulls the configs without adding `__init__.py` files is in a coherent state, since
  `extraPaths` alone was measured to cost nothing on an unpackaged tree, and the ban is inert in a
  flat-layout consumer with no `src/` at all. So the only thing the sweep records is a window in
  which the family is mixed. What it should check per consumer: that adding the three `__init__.py`
  files is a separate, deliberate decision in that repo rather than something `configs.pull`
  implies.
- The security-workflow caller, from the now-retired `plans/2026-08-30-deps-audit-in-ci.md`. Each
  repo in the family needs about six lines — a `.github/workflows/security.yml` whose one meaningful
  line is a job-level `uses:` naming this repo's `security-reusable.yml` at a full 40-character SHA,
  with the readable version in a trailing comment. `repo-tasks` calls its own copy by relative path
  and is done; the other eight are not, so the uniformity the design exists for is potential rather
  than actual. **This one is an addition to each consumer rather than a `configs.pull`**, which is
  what makes it sweep work rather than something a consumer picks up on its own schedule.
  `scaffoldapy` is excluded from this item and is the highest-leverage repo of the set — its
  template would hand the caller to every generated repo for free — and it is already filed there as
  `plans/2026-08-31-security-workflow-caller.md`. Note while doing it that a pinned caller currently
  goes stale silently, per [`../contributing/quality-gate.md`](../contributing/quality-gate.md).
- **Report-mode wiring**, moved here 2026-09-08 from the retired run-reporting plan, which could not
  be retired while it still carried the rollout. `power-user-linux-setup` is verified and done. The
  `scaffoldapy`-generated repos and the `*-polite-mcp` family take `repo-tasks` as a pinned
  dependency and none has been bumped. **This is the item where "the consumer looks fine" is not
  evidence**: a consumer that hand-builds its own root `Collection` needs
  `runner.configure(namespace)` in its `tasks.py`, and without it the exported variable does nothing
  there while the output is byte-identical to a wired consumer with the variable unset. There is
  nothing to read it off, so `rg -n 'runner.configure' tasks/` is the check — it is already in
  [`../contributing/consumer-sweep.md`](../contributing/consumer-sweep.md), and the reasoning is in
  [`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Turning it on in a
  consumer". Two questions sit downstream of this and belong to the repos that own them, not to the
  sweep: whether `scaffoldapy`'s template should carry the call by default (filed there as
  `plans/2026-09-06-report-mode-wiring-in-the-generated-tasks-py.md`, which also asks the larger
  question of whether the generated `tasks.py` needs its own root `Collection` at all), and whether
  report mode actually moves the piped-gate rate, which `power-user-linux-setup`'s
  `plans/2026-09-05-pipefail-in-the-agent-shell.md` owns along with the baseline to compare
  against.]

[PITFALL: **this list was the sweep's only definition of scope, and nothing added to it — which is
why it is no longer the definition of anything.** Every entry was written by the session that landed
the change, which works exactly as long as every such session remembers, and two did not: `7fc0b23`
and `487c9c8` were both found by a later audit reading the source, four days and same-day
respectively, and `7fc0b23` is a gate step that can turn a consumer red. A missing entry is
invisible in the worst way, because the list looks complete and the sweep that runs from it reports
success.

Retained because the mechanism recurred at a level the fix did not reach. The answer to a missing
_item_ was "derive the items" — `configs.diff` — and that holds; the list of **repos** stayed
hand-kept and was wrong twice more, most recently on 2026-09-13, for exactly the reason stated here.
Deriving one list did not make the other one safe, and the correction that closed the first is the
same shape as the claim that broke the second.]

## The batched sweep's first half ran (2026-09-05): `power-user-linux-setup`

32 commits' worth, `9d57d464` -> `7bb880b0`. **`scaffoldapy` is untouched and still owes the other
half**, including the e2e tier that is the only thing in the family testing what it generates — so
the `[DEFERRED:]` above is half discharged, not closed.

What ran: `inv deps.lock --package repo-tasks`, `uv sync`, `configs.pull`, `configs.ensure-deps`,
`deps.lock`, `uv sync`, gate. Two corrections to `contributing/consumer-sweep.md` came out of
walking it, and are made there rather than left here: **the pin bump belongs above `configs.diff`
for a lock-pinning consumer** (running `diff` first reports drift against the _old_ shipped configs
and a `pull` then writes them — an identical report before and after the bump, which reads as though
the bump changed nothing), and `inv venv.sync` has no meaning in a consumer publishing no `venv`
collection, where plain `uv sync` is the step.

### Which way each prediction went

| item                                   | prediction                       | outcome                                          |
| -------------------------------------- | -------------------------------- | ------------------------------------------------ |
| `ae54087` `pytest-socket`/`pytest-cov` | `configs.diff` exits 1, CI green | **diff fired**; `pytest-timeout` was missing too |
| `8f384d7` `pytest.ini` ResourceWarning | inert here                       | **inert** — 573 tests, no change in outcome      |
| `949607c` `ruff.toml` `target-version` | check `requires-python` exists   | **exists** (`>=3.11`), linter stays at 3.11      |
| `c514bd9` derived `pythonVersion`      | can turn a green consumer red    | **it did** — the one real finding, below         |
| `c514bd9` derived `anyio_mode`         | emitted iff the lock has AnyIO   | **emitted**, correctly — AnyIO is in that lock   |
| packaged-`tests/` pair                 | inert, no ordering hazard        | **inert** — no `src/`, `tests/` left unpackaged  |
| `b79b76a` `--python-version`           | additive, nothing to check       | present, unused                                  |
| `de596ce` `venv.check`/`venv.recreate` | reports a mismatch everywhere    | **not run** — no `venv` collection published     |
| `3a58b1d` `docs.link-check` fix        | could turn red to green          | no change; that repo's docs were already green   |

**Both halves of `configs.diff` fired on the same run for the first time**, as the section above
predicted they would: config-file drift on three files and dev-group drift on two entries.

### The one real finding, and it is the predicted one

**`pythonVersion` derived into `pyrightconfig.json` moved the type checker from the developer's 3.14
venv to the declared 3.11 floor, and two test modules failed immediately** —
`from typing import
override`, which is 3.12+. They had been passing only because nothing was
checking at the floor. That repo had even declared `typing-extensions` as a dev dependency for
exactly this, with a comment saying so, and a third test module already used the right import; the
two others had simply drifted.

This is the finding rather than a regression, and it is the strongest evidence the sweep produced:
`c514bd9` is doing precisely what its design says, on the first consumer it reached.

**CI is green, so the prediction holds for this consumer.** Pushed 2026-09-05; run `33985012776` and
its siblings on `d193783` report `success` for `CI`, `Deploy docs to GitHub Pages` and
`Dependency Graph`. That is the half that could not be tested locally, and it went the way this plan
said it would: `configs.diff` fired on both halves while nothing in CI changed outcome, because none
of the pending changes is a binary a gate step shells out to.

[UNVERIFIED: **still unanswered, and this sweep could not answer it** — the `[UNVERIFIED:]` above
about `require_tool`'s preflight never having fired from a consumer's own CI. None of these changes
is a gate binary, so nothing here could make it fire. It waits on the first family-wide manifest
change that adds one.]

This section is merged in from `2026-09-05-power-user-linux-setup-swept.md`, filed for this repo
from that consumer's own session (`25ea8788-b99d-43a2-9611-2d0c1f207694.jsonl`, around
2026-09-05T18:00Z) and absorbed 2026-09-06 — the name to search for with `plans.py archive` if the
original filing is ever wanted.

## What both consumers are actually behind on (measured 2026-09-08, read-only)

Measured rather than read off the checklist, by running the **installed `v0.3.0` tool's** own
`configs.diff` and `link_check` against each consumer's tree from outside it — no write, no pull,
and nothing in either working tree touched. Both consumers report **identical** drift:

| item                                                 | on the checklist above? |
| ---------------------------------------------------- | ----------------------- |
| `ruff.toml` — the `sys.path`/`site.addsitedir` bans  | **no**                  |
| `dprint.json` — sha256 checksums on all five plugins | **no**                  |
| `pytest.ini` — the starlette `anyio` ignore          | yes (added 2026-09-08)  |
| dev group — `hadolint-py` missing `!=2.15.1.2`       | **no**                  |

[PITFALL: **the checklist was missing three of the four, and the pitfall above understated it at
two.** Both entries found by reading source that day were real, and measurement then found two more
that no amount of re-reading the plan would have surfaced — the `ruff.toml` coupling bans and the
`dprint.json` checksums, each landed by a session that had no reason to think of this file. That
settles the question the pitfall left open: the sweep cannot start from this list. `configs.diff`
against the installed tool **is** the list, and it takes one command per consumer.]

**`power-user-linux-setup` was swept on 2026-09-05 and is already behind again on three items**,
which is the same point from the other end: the list is not merely incomplete, it is a snapshot of a
moving target, and a sweep is only current on the day it runs.

### The anchor-check prediction, falsified

The `7fc0b23` item was sequenced first above on the grounds that a stricter link check can turn a
green consumer red on links nothing has ever checked. **It does not, for either consumer** — the
v0.3.0 `link_check` reports no broken links against `scaffoldapy` or `power-user-linux-setup`. The
risk was real in kind and empty in fact, and the ordering it justified can be dropped.

[PITFALL: **`scaffoldapy` was never behind on that item at all**, and the checklist entry would have
sent someone looking. It consumes `repo-tasks` as the **global uv tool**, which is already `v0.3.0`,
so every task-code change — the anchor check included — has been live there since the moment the
tool moved. Only the pulled config _files_ and the dev group are snapshots that drift. The two
consumers are behind in genuinely different ways, and the checklist's flat list of commits does not
express that: `power-user-linux-setup` pins `repo-tasks` in its own lock, so task code and configs
both lag; `scaffoldapy` lags on configs only.]

## The consumer set is three, not two (2026-09-10)

**Superseded 2026-09-13: it is six, and the one-command check this section ends on is what held it
at three.** The flavour reasoning below still holds and the rows in its table are still right about
the repos they name; the membership is not. See "The consumer set is six" at the end of this file
before using either.

Carried here from the retired `2026-08-28-node20-action-deprecation.md`, which had deferred "worth
checking whether `scaffoldapy` and `agent-skills` publish the `ci` namespace either" after finding
that `power-user-linux-setup` did not.

**Both publish it, by the strongest route available**: each repo's `tasks.py` is
`from repo_tasks import ns`, so every namespace this package ships is live there the moment their
tool moves — `ci.status` and `ci.check-actions` included. Neither needed the wiring
`power-user-linux-setup` needed, because neither builds its own collection.

[PITFALL: **`agent-skills` was recorded as not a consumer at all, and it has been one since its
first commit.** The node20 plan stated on 2026-09-09 that it had "no `from repo_tasks` in its tasks,
no bootstrap script"; both files are there in `9e49f39`, 2026-08-27. That claim was wrong when
written rather than gone stale, and it had a consequence — it routed that repo's action work out of
"the batched consumer sweep" as a category error, when the category was right and only the sweep's
membership list was short. Check the file, not the memory of the file: the whole consumer set is
`rg -l 'from repo_tasks' <projects root>/*/*/tasks.py`, which takes one command.]

So the flavours, corrected — and it is the flavour rather than the count that this plan needs:

| consumer                 | how it consumes              | what lags                 | regenerates from the namespace |
| ------------------------ | ---------------------------- | ------------------------- | ------------------------------ |
| `power-user-linux-setup` | pinned in its own lock       | task code **and** configs | yes — a task index             |
| `scaffoldapy`            | the global `uv tool` install | configs only              | no                             |
| `agent-skills`           | the global `uv tool` install | configs only              | no                             |
| `repo-tasks` itself      | dogfoods its own `ns`        | n/a                       | yes — the requirements table   |

The fourth column is not the same information as "builds its own collection", which is what it was
first suspected of duplicating. `repo-tasks` imports its own `ns` and regenerates; `scaffoldapy`
builds its own collection in the repos it **generates** while importing `ns` itself, and regenerates
nothing. Measured 2026-09-12 rather than reasoned about:
`rg -l 'render-docs|ensure_block|BEGIN
GENERATED'` finds nothing in `scaffoldapy` or `agent-skills`.
It earns the column because it decides whether a sweep there can be split into separately-gated
commits at all.

`agent-skills` also carries the family's last action-currency residue — two
`astral-sh/setup-uv@v9.0.0` pins against `v10.0.1`, which its own `inv ci.check-actions` can see.
Filed for that repo as `2026-09-10-setup-uv-pins-two-majors-behind.md` rather than swept from here,
since the reading of v10's cache change has to be done against its workflows, the Windows job
included.

## The lock-pinning consumer is swept to `v0.3.0` (2026-09-10)

Merged in from `2026-09-10-power-user-linux-setup-swept-to-v0-3-0.md`, filed into the store by the
session that did the work there and absorbed here 2026-09-12 — the name to search for with
`plans.py archive` if the original filing is wanted. Merged rather than kept beside this plan
because it reports on this plan's own subject and says so: its recommended direction is "advance
`2026-08-25-consumer-transitions.md` on the strength of this".

**All four items from the 2026-09-08 measurement are closed**, in four commits on that repo's
`master`, pushed: `14d7796` bumped the pin `0.2.0` (`7bb880b0`) → `0.3.0` (`46d28604`) with
`docs/tasks.md`; `846b6c7` pulled `ruff.toml`, `dprint.json` and `pytest.ini`; `96df342` took
`hadolint-py!=2.15.1.2` and its lock effect; `31aacd4` landed that repo's own sweep plan. Verified
there with `inv configs.diff` reporting up to date, `inv quality.precommit` PASS at 16 steps, and
`inv docs.link-check` silent.

**The pitfall above is confirmed rather than merely argued.** `configs.diff` named exactly the items
it predicted, in that order, with the `hadolint-py` line arriving as next-steps output rather than
as a file diff — nothing missing, nothing extra. The sweep cannot start from a hand-maintained list,
and `configs.diff` **is** the list.

**The link-check prediction is dead in both directions.** It was falsified from outside, by running
the global `v0.3.0` `link_check` against that tree; run from inside afterwards, with the strict
version resolved from that repo's own lock, `inv docs.link-check` still reports nothing.

[PITFALL: **a generated docs artifact is not separable from the pin bump**, which breaks the
gated-commit split this plan's sweep assumes. That consumer regenerates a task index from the live
namespace; `v0.3.0` reworded a `configs.diff` docstring, so its `test_catalog` fails on the pin
commit alone. The bump and the regeneration have to land together. The symptom is what makes this
worth recording — a test failing on a commit that touched only a lock file reads as a broken bump
rather than as a missing regeneration. Likely specific to that consumer, since it is the one that
builds its own collection and so the one with a namespace-derived artifact.]

**The `configs.require_tool` `[UNVERIFIED:]` above is untouched by this sweep**, and is not closed
by association: none of the four items is a gate binary, so that run could not have fired the
preflight from a consumer's own CI.

~~Does [`../contributing/consumer-sweep.md`](../contributing/consumer-sweep.md) want the
generated-artifact clause?~~ **Yes**, added 2026-09-12. The objection — dead text for two of three
consumers — dissolves once the clause is written **conditionally**: "where a consumer regenerates
anything from the live namespace" skips itself in a repo that does not, and carries a one-command
test (`rg -n '^\[docs\]' repo-tasks.toml`) so a reader settles it rather than remembering it. Dead
text is a paragraph that applies to nobody, not a guarded one that applies to somebody.

It is also smaller than it looked. `docs.generate` is the first step of `fix`, so the sweep's
existing `inv quality.precommit` already does the regenerating; what the doc was missing was only
how the result gets committed — which is the half that fails confusingly.

~~Does the flavour table want a fourth column for namespace regeneration?~~ **Yes**, added above —
and the premise that it duplicates "builds its own collection" is wrong, which is why it was worth
checking rather than reasoning about. `repo-tasks` imports its own `ns` and regenerates;
`scaffoldapy` builds its own collection only in the repos it generates, and regenerates nothing
itself. Two of the four rows differ from what the implication would have predicted.

## The consumer set is six (2026-09-13)

The section above ends on a recipe — "the whole consumer set is
`rg -l 'from repo_tasks' <projects root>/*/*/tasks.py`, which takes one command" — written in the
same breath as a pitfall about checking the file rather than the memory of the file. Run today, that
command is wrong in both directions at once.

**It misses a consumer the same section tabulates two paragraphs later.** `power-user-linux-setup`
has no `tasks.py`; it has a `tasks/` package, and its `from repo_tasks import ...` sits _inside a
function_ in `tasks/__init__.py`, deliberately, so that a missing tool degrades one command instead
of every command. A glob ending in `tasks.py` cannot see either shape, and a search for a top-level
`from repo_tasks` would not see the second one anywhere.

**And it finds two repos nobody has recorded as consumers at all.** Neither is trivia: each carries
the shipped `ruff.toml`, `pytest.ini`, `pyrightconfig.json` and `dprint.json`, so each drifts in
exactly the way this plan exists to catch.

| consumer       | how it consumes                    | what lags                 | named in this plan? |
| -------------- | ---------------------------------- | ------------------------- | ------------------- |
| `ingesta`      | the global `uv tool` install       | configs only              | never               |
| `invoke-stubs` | `repo-tasks` as its own dependency | task code **and** configs | never               |

`ingesta` carries a stamped `bootstrap-repo-tasks.sh` too, so it answers every test this plan uses.

`invoke-stubs` is a third flavour rather than a second copy of `power-user-linux-setup`'s, and its
own `pyproject.toml` says why it is allowed to be: the family's standing objection to depending on
`repo-tasks` is that the dependency brings `invoke` with it and a second `inv` on PATH shadows the
global tool with one that cannot import `repo_tasks` — which does not apply where `repo_tasks` is in
that project's own environment. That is the same shadowing
[`2026-09-08-status-measures-the-running-interpreter-not-the-global-tool.md`](2026-09-08-status-measures-the-running-interpreter-not-the-global-tool.md)
made `repo-tasks.update` report, seen from the one side that is entitled to it.

So the batched sweep, scoped as it is everywhere above, would have covered **two of the five**
non-self consumers.

[PITFALL: **this is the third membership count in three weeks and the first two were both wrong, and
each answer came from a shape somebody expected rather than from what makes a repo a consumer.** Two
on 2026-08-25, three on 2026-09-10, six today. The 2026-09-10 correction is the sharpest case,
because the one-liner it prescribed to stop the problem recurring is what hid the next two: it
encodes "a consumer has a `tasks.py` with a top-level `from repo_tasks`", and three of the six do
not. A repo consumes this package if it resolves `repo_tasks` at all, and no path shape is entitled
to stand in for that.]

Measured with `rg -l 'repo_tasks' <projects root> --glob '**/tasks.py' --glob '**/tasks/*.py'`,
which returns all six plus `scaffoldapy`'s template. Two things about it are deliberate and worth
carrying: it matches the **string** rather than a `from` import, which is what reaches the lazy one,
and it therefore returns comments and prose too — so it is a list to read rather than a list to
count. `ingesta` and `power-user-linux-setup` both matched on comments first. It is still a shape,
and a repo wiring its tasks from some other file would still be missed; the honest form of this
question is a search plus a reading, not a one-liner, which is the whole of the pitfall above.

### What the three unswept consumers are behind on (measured 2026-09-13, read-only)

Measured rather than deferred, because it is one command three times. Each run is the **installed
`v0.3.0` tool's** own `configs.diff` against that repo's tree, from a subprocess that chdirs into it
— no write, no pull, nothing in any working tree touched, and the same tool version for all three so
the answers are comparable.

| consumer       | config files behind                       | dev group                                                                  |
| -------------- | ----------------------------------------- | -------------------------------------------------------------------------- |
| `scaffoldapy`  | `ruff.toml`, `dprint.json`, `pytest.ini`  | `hadolint-py` unconstrained                                                |
| `ingesta`      | those three **plus `pyrightconfig.json`** | **missing `pytest-socket`, `pytest-timeout`**; `hadolint-py` unconstrained |
| `invoke-stubs` | `ruff.toml`, `pytest.ini`                 | **missing `invoke-stubs`** — see the pitfall below                         |

**`scaffoldapy` is unchanged from the 2026-09-08 measurement**, item for item, so the table in its
filed sweep plan is still current five days on and that plan wants no re-scoping.

**`ingesta` is the worst of the three, and has never been named anywhere.** A fourth config file
behind, and a dev group missing two manifest entries outright rather than merely unconstrained —
which is the `ae54087` drift this plan has tracked since 2026-08-29, sitting unaddressed in a repo
the tracking never covered.

[PITFALL: **the manifest cannot be spliced into a consumer that is itself one of its entries, and
`configs.diff` is right now telling `invoke-stubs` to add itself.** `repo-tasks-quality` lists
`invoke-stubs @ git+https://github.com/TheodoreAD/invoke-stubs`, so the dev-group half reports it
missing there and the next-steps block prescribes `configs.ensure-deps` — which would splice a
dependency on its own git remote into that repo's `dependency-groups.dev`. Its `pyproject.toml`
records that its quality group was "put in place by `repo-tasks configs.ensure-deps` rather than
hand-listed", so that is the live path and not a hypothetical.

This repo never hits it because it solves the same problem a different way: `dev` here is
`[{ include-group = "repo-tasks-quality" }]`, which is the shape `configs.diff`'s own docstring
already records `_DEV_ARRAY_RE` as reading like a declaration of nothing. The case is understood one
layer down and unhandled one layer up. A consumer that is itself a manifest entry needs either an
exclusion in `ensure_deps` or a documented "not here", and **the sweep must not run `ensure-deps`
against `invoke-stubs` until that is decided.**]

[DEFERRED: whether `ingesta` and `invoke-stubs` are in the sweep's scope at all — the user's call,
which the measurement above is meant to inform rather than presume. What it settles is that
"unknown" has stopped being an argument either way: both are consumers by every test this plan
applies, and `ingesta` is drifting on precisely the items the batched sweep exists for. Nothing has
been written to either tree.]

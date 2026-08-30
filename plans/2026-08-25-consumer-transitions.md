---
status: in-progress
updated: 2026-08-28
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
forgotten — that distinction is the whole reason this section exists rather than a memory entry.]

## The second unswept change (2026-08-29) — the sweep is now batched

`8f384d7` added `ignore:unclosed file:ResourceWarning` to the shipped `pytest.ini`
([`2026-08-26-integration-tier-version-fixture.md`](2026-08-26-integration-tier-version-fixture.md)
has why). The sweep was deferred again, deliberately and at the user's direction: more work is
landing here first, and one sweep covering everything accumulated is cheaper than one per change.

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

[DEFERRED: one batched sweep once the current run of work here is done. Record which way each
prediction went — the `[UNVERIFIED:]` above is still waiting on a preflight that has never fired
from a consumer's own CI, and none of the changes below will make it fire, since none is a gate
binary. What the sweep has to cover, kept here rather than in a session handoff so it survives the
session that wrote it:

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
  on the floor rather than the newest.]

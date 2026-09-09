---
status: landed
updated: 2026-09-10
---

# What a version number means here, and cutting the first real release

## Context

Raised by the user 2026-09-04: dogfood releasing in this repo, since this repo is the mechanism the
rest of the family will use for it. Stay on `0.X.Y` until the package is fully developed, and do not
spend effort deciding whether a change is breaking.

**Almost all of this plan landed on 2026-09-04 and its content is no longer here.** Reconciled
2026-09-05, when the plan was found still listing as open what the code had answered the same day it
was last edited:

- The versioning rule — minor means the shipped surface moved, patch means it did not, with the
  thirteen-entry surface audit and the one-line test — is
  [`../contributing/versioning.md`](../contributing/versioning.md), "What minor and patch mean
  here".
- The release mechanism is `release.py` (`a04b2ce`, `33017fa`): `release.push-tag` as the deliberate
  gate, `release.create` for the GitHub Release, both model-agnostic; `trunkflow.cut` (`e1d0306`)
  pushes nothing by default (`cc49ebb`). The reasoning, including the survey of how `requests`,
  `flask`, `httpx` and `uv` trigger publication, is in
  [`../contributing/release-flow.md`](../contributing/release-flow.md), "The trunk flow, end to
  end".
- A release is never automatic, and the task is the primitive with a `workflow_dispatch` workflow
  calling it: `.github/workflows/release.yml`, whose header carries the decision and why it is the
  opposite call from `security-reusable.yml`.
- `publish.yml`'s tag trigger, which made `trunkflow.cut` mean "upload to TestPyPI", is removed
  (`02c3ed7`); that file's header records both pitfalls.
- `v0.2.0` was cut with `trunkflow.cut` (`cef6894`) and the tag is on origin. It is a minor under
  the rule: the packaged-tests configs, the ruff `banned-api` entry, `pytest-timeout` in the
  manifest and the reusable workflow had all moved since `0.1.0`.

## What is left

~~**The GitHub Release for `v0.2.0` has not been created.**~~ Superseded 2026-09-08 — see the
release below. The pitfall it was holding open, in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Consumers pin a full SHA", is
now closed rather than merely undegraded.

## `v0.3.0` was cut and released, 2026-09-08

At the user's request, and `v0.2.0`'s Release was skipped rather than created retroactively — a
Release exists to be `releases/latest`, and cutting the newer version answered that question without
publishing a superseded one.

**Minor, decided mechanically rather than by assessment**, which is what the rule in
[`../contributing/versioning.md`](../contributing/versioning.md) is for. Diffing the enumerated
surface over the 125 commits since `v0.2.0` showed four shipped files moved — `pytest.ini`,
`ruff.toml`, `dprint.json`, and the `repo-tasks-quality` entries in `pyproject.toml` — plus three
new task modules (`runner.py`, `interactive.py`, `nextsteps.py`), and module names are API here. No
judgement call was needed at any point, which is the rule working.

The documented three-step sequence ran as written: `trunkflow.cut --bump minor`, then
`release.push-tag`, then `release.create`. Gate green on the bump commit, and CI green on it after
the push.

[PITFALL: **the safety property that makes a tag push cheap is worth re-checking rather than
remembering, because it was once false in this very repo.** `publish.yml` used to fire on
`push: tags: v*` with an unconditional TestPyPI job, so a cut meant an upload. Confirmed before
pushing 2026-09-08: that file is `workflow_dispatch:` only and no workflow in the repo triggers on
tags at all, so the tag reached no index. That check costs one `rg` and is the difference between a
version number and a publication.]

**`ci.check-actions`' stale-pin check is now live**, which was the stated reason the Release
mattered. It cannot be observed from this repo — this repo calls its own reusable workflow by
relative path, which resolves to no `owner/repo`, so the check correctly prints no line for it. The
evidence is one step lower: `gh api repos/<this repo>/releases/latest --jq .tag_name` returns
`v0.3.0` where it previously 404'd, and a 404 is exactly what `_latest_tag` turns into `None` and
skips. A consumer pinning `security-reusable.yml` at a SHA will now get a verdict instead of
silence.

**The global install on this machine was moved to `v0.3.0`** with `inv repo-tasks.update`. That
surfaced a real defect in `repo-tasks.status`, which reported `0.2.0` immediately after a successful
upgrade — filed as
[`2026-09-08-status-measures-the-running-interpreter-not-the-global-tool.md`](2026-09-08-status-measures-the-running-interpreter-not-the-global-tool.md),
because the fix needs a decision this plan should not make in passing.

**Deliberately not done: `inv repo-tasks.stamp`.** Pinning consumers is not a step in cutting a
release — it is the open "is the fix pinning, or a release cadence?" question in
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md), and stamping would have
answered it silently by making every consumer stop tracking `main`. `bootstrap-repo-tasks.sh` stays
unpinned until that is decided on its own terms.

**A task that computes the part for you** — `inv version.next-part --since v0.2.0` — moved
2026-09-10 to [`2026-09-10-version-next-part-task.md`](2026-09-10-version-next-part-task.md), with
the reason it was deferred intact: the rule has been used for real exactly once, and each further
release is free evidence about what the task would have to get right.

~~Does `repo-tasks` want a moving `stable` tag as well?~~ **No**, ruled out by the user 2026-09-10.
It answers "what should I install"; every question this repo's consumers actually put is "what am I
pinned to" — they pin `security-reusable.yml` at a SHA, `ci.check-actions` reads Releases rather
than tags, and `bootstrap-repo-tasks.sh` installs from the default branch unpinned by design.
Recorded in [`../contributing/versioning.md`](../contributing/versioning.md), "One version, three
spellings", including the one condition that would reopen it: pointing the bootstrap script at a
ref, which is `2026-08-25-consumer-transitions.md`'s pinning-versus-cadence question and not this
plan's to answer.

A false alarm worth keeping so nobody re-finds it: `docker-release.yml` looks like it triggers on
`release:`, which would couple `release.create` to an image push. It does not — that `release:` is
the **job name**; the workflow is `workflow_dispatch` only. Grepping `^  release:` in a workflow
finds both, and they mean opposite things.

## Recommended direction

The release this plan was waiting on has happened, so what is left is the `stable` question above
and nothing else. Answer it, then this plan lands and retires — the versioning rule and the release
mechanism both have permanent homes in `contributing/` already, so the retirement is mostly a
question of whether anything in the `v0.3.0` section is worth keeping there. Two candidates: the
check-before-you-push pitfall, and the note that the stale-pin check cannot be observed from this
repo, which will otherwise be re-derived by whoever next wonders why `check-actions` says nothing
about it.

The deferred `next-part` task stays deferred. It was to be reconsidered once the rule had been
applied a few times; it has now been applied twice, both times in under a minute with an unambiguous
answer, which is evidence against building it rather than for.

## Migrated to

Retired 2026-09-10. The release this plan was cut to dogfood happened on 2026-09-08 and the last
open question — a moving `stable` tag — was ruled out by the user on 2026-09-10, so nothing here is
live.

**[`../contributing/versioning.md`](../contributing/versioning.md)**: the `stable`-tag decision, in
"One version, three spellings", including the single condition that would reopen it; and, under the
minor-versus-patch rule, that the rule was exercised for real on `v0.3.0` and produced its answer
from a diff with no judgement call at any point. That last is the only evidence the rule has, and
the rule is the plan's whole subject.

**[`../contributing/release-flow.md`](../contributing/release-flow.md)**, beside the existing
tag-trigger pitfall: that the property making a tag push cheap is re-checked before each push rather
than remembered, since it was once false here; and the `release:`-is-a-job-name false alarm, which
reads exactly like a trigger coupling `release.create` to an image push.

**[`../contributing/quality-gate.md`](../contributing/quality-gate.md)**: the stale-pin pitfall
there claimed the currency check could not work for a consumer's pin "yet", which stopped being true
when `v0.3.0` was released. Corrected, and the reason the check prints nothing when run _here_ — a
relative-path reusable workflow resolves to no `owner/repo` — recorded beside it, with the
one-level- down check that does answer.

**[`2026-09-10-version-next-part-task.md`](2026-09-10-version-next-part-task.md)**: the deferred
`version.next-part` task, carried with the evidence that now argues against building it.

Deliberately not migrated:

- **The `v0.2.0`-versus-`v0.3.0` sequencing** — why the older Release was skipped rather than
  created retroactively. It is a decision about one release, not about how releases work.
- **The three-step run log and the CI-green confirmations.** `release-flow.md` documents the
  sequence; that it ran as written is what a commit message is for.
- **`repo-tasks.stamp` deliberately not run.** It belongs to
  [`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md)'s open
  pinning-versus-cadence question, which is live and already states it.
- **The `repo-tasks.status` defect** found while upgrading the global tool — already its own plan,
  [`2026-09-08-status-measures-the-running-interpreter-not-the-global-tool.md`](2026-09-08-status-measures-the-running-interpreter-not-the-global-tool.md).

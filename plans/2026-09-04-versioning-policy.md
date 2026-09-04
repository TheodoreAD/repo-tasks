---
status: blocked on the user wanting releases, which wait for real artifact stores to release into
updated: 2026-09-05
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

**The GitHub Release for `v0.2.0` has not been created.** `inv release.create --tag v0.2.0` is one
task run — `gh` is authenticated and the tag is on origin, so nothing else is needed — and it is the
step that turns `ci.check-actions`' stale-pin check on, since that check reads `releases/latest` and
a tag is not a Release. The user parked it 2026-09-05: no releases yet, those would need actual
artifact stores to work with. Until then the pitfall recorded in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Consumers pin a full SHA",
stays live: a pinned consumer goes stale silently. There are no pinned consumers today (checked
2026-09-04), so nothing is degraded by waiting.

[DEFERRED: **a task that computes the part for you.** `inv version.next-part --since v0.2.0` diffing
the surfaces enumerated in `versioning.md` and printing `minor` or `patch` is the natural end state,
and it is exactly the kind of thing this package exists to hand other repos. Not needed for the
first release, and designing it before the rule has been used a few times would be the wrong order.]

[NEEDS CLARIFICATION: does `repo-tasks` want a moving `stable` tag as well, the convention
`power-user-linux-setup` uses? It is a different mechanism for a different question — `stable` says
"what should I install", version tags say "what am I pinned to" — so they are complementary rather
than alternatives. Probably not needed here, since consumers pin SHAs and the currency check reads
Releases, but it is the convention the user named and worth ruling in or out deliberately.]

A false alarm worth keeping so nobody re-finds it: `docker-release.yml` looks like it triggers on
`release:`, which would couple `release.create` to an image push. It does not — that `release:` is
the **job name**; the workflow is `workflow_dispatch` only. Grepping `^  release:` in a workflow
finds both, and they mean opposite things.

## Recommended direction

Nothing until the user wants releases. When they do: `inv release.create --tag v0.2.0`, confirm
`ci.check-actions` now reports the reusable workflow's pin as current or stale rather than skipping
it, then land and retire this plan. The `stable` question can be answered in the same session, and
the deferred `next-part` task becomes its own plan if the rule turns out to be tedious to apply by
hand.

---
status: idea
updated: 2026-08-25
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
   moved to that commit. `plans/2026-08-25-type-check-warning-noise.md` had recorded "scaffoldapy is
   unaffected (verified)", which was true of scaffoldapy's own tree and false of what it generates.

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

- [NEEDS CLARIFICATION: should a gate step that needs a binary preflight for it and stop with the
  fix, per task-module-conventions' "stop loudly and say what to run next" — e.g. `workflow_check`
  checking `shutil.which("actionlint")` and failing with "actionlint missing from this project's dev
  group — run `repo-tasks configs.ensure-deps` then `inv deps.lock`" — instead of the shell's exit
  127? Cheap, and it converts the worst symptom into a one-line fix. Against: every tool-running
  task would need it, and the real defect is the drift, not the message.]
- [NEEDS CLARIFICATION: should `configs.diff` (and `repo-tasks.status`) report dev-group drift
  against `repo-tasks-quality` the way `diff` already reports drifted config files? A consumer would
  then see "dev group missing: actionlint-py, act-bin" from the same command that already tells it
  its `pyrightconfig.json` is stale. Moved here from `scaffoldapy`'s retired
  `plans/2026-08-25-ci-missing-actionlint.md`, which raised it and said it belongs to this repo.]
- [NEEDS CLARIFICATION: is the fix pinning, or a release cadence? The moment a `v0.1.0` tag exists,
  `stamp` pins consumers to it and `repo-tasks.update` targets tags — the machinery is built
  (`contributing/release-flow.md`) and unused. Pinned consumers stop tracking `main`, which turns
  each of these incidents into a deliberate per-consumer update. The cost is that a fix here reaches
  nobody until released, and every consumer has to be walked forward — which is the "consumer sweep"
  below either way.]
- [NEEDS CLARIFICATION: what is the consumer sweep, concretely? When `repo-tasks-quality` or a
  shipped config changes, which repos need `inv repo-tasks.update` + `configs.ensure-deps` +
  `deps.lock` + `configs.pull` + gate, and where is that list? Known today: `power-user-linux-setup`
  (did it by hand, `395dc3d`), `scaffoldapy` (did it by hand, `56d80e8`, plus template fixes
  `2e29f2b`), the `*-polite-mcp` repos and `product-research-pipeline` (status unknown). A checklist
  in `contributing/` is the minimum; a task that runs the sweep against a list of local checkouts is
  the mechanism.]
- [NEEDS CLARIFICATION: should `scaffoldapy`'s e2e be this repo's canary — run before merging a
  change to `repo-tasks-quality`, `configs/`, or any `quality.*` composite? Locally that is
  `inv repo-tasks.update` from this checkout (or a `uv tool install` of the working tree) followed
  by `inv test.integration` in `scaffoldapy`. In CI it would be a cross-repo job: check out
  `scaffoldapy`, bootstrap repo-tasks from the PR's ref instead of `main`, run its integration tier.
  ~2 min, and it would have caught both incidents before merge.]

## Recommended direction

Rough, in order of payoff per effort:

1. Preflight-with-fix in the gate steps that shell out to a group-installed tool, so the failure
   names the command that fixes it. Smallest change, immediate.
2. Dev-group drift in `configs.diff`, so a consumer running its existing drift check sees the whole
   picture.
3. Write the consumer sweep down in `contributing/` now (the list of consumers and the five
   commands), and decide separately whether it becomes a task.
4. The `scaffoldapy` canary as a CI job here — the only item that catches a break _before_ it ships.
5. Tagging a release is a policy decision that changes what all of the above defends against; take
   it when the release flow is exercised for real, not as part of this plan.

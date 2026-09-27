---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/power-user-linux-setup
source_session: b73129dd-6136-41c3-a026-8e871581bc14.jsonl
source_moment: 2026-09-27T21:10:00Z
source_plan: plans/2026-09-27-sweep-to-repo-tasks-v0-5-0.md
---

# Zizmor self repository audit conflicts with actionlint and act

## Context

`zizmor` 1.30.0 added the `self-repository` audit: every workspace-relative `uses: ./...` (a local
action or reusable workflow) is flagged, with the fix `uses: $/...` — GitHub's self-repository
syntax, announced 2026-07-30. It is a `low` finding with an auto-fix marked unsafe, and it fails
`quality.workflow-check`, so **every consumer with a local reusable-workflow call goes red the
moment its lock takes zizmor 1.30**.

The fix is not takeable today, because the gate's other two readers of the same files reject it:

- **actionlint** (`rhysd/actionlint`, `main@011a6d1`): `rule_workflow_call.go:64-73` accepts only
  `./path/to/workflow.yml` or `owner/repo/path/to/workflow.yml@ref`; anything else is "not following
  the format". No `$/` handling anywhere in the tree.
- **act** (`nektos/act`, `master@4f41128`): `pkg/model/workflow.go` `Job.Type()` classifies a
  reusable workflow as local only on a `./` prefix, and returns `JobTypeInvalid` with an error for
  anything else — so `test.workflows` (which drives `act`) would break on the rewritten form.

Both clones are in `$RESEARCH_HOME/repos/`, as is `zizmorcore/zizmor` (`docs/audits.md`,
`## self-repository`, for the audit's rationale).

## Evidence

Hit sweeping `power-user-linux-setup` to v0.5.0, 2026-09-28: taking zizmor 1.29.0 → 1.30.1 turned
the gate red with four `help[self-repository]` findings, on `ci.yml:18`, `ci.yml:73`,
`devcontainer.yml:78` and `devcontainer.yml:85`. That consumer declined them inline
(`# zizmor: ignore[self-repository]`, reasoning beside the first call in `ci.yml`) because its
`zizmor.yml` is a pulled config, and a local disable there would read as drift on the next
`configs.diff`.

## Open questions

[NEEDS CLARIFICATION: disable the audit in the shipped `zizmor.yml` family-wide, or leave each
consumer to suppress inline? Shipped is one edit and covers consumers not yet swept, but it hides
the audit in every repo until someone remembers to lift it; inline puts the reason next to the line
but repeats in every consumer.]

## Recommended direction

Disable `self-repository` in the shipped `zizmor.yml` (`rules: self-repository: disable: true`),
with a comment naming the two blockers and the condition for lifting it: both actionlint and act
accept `$/`. The conflict is a property of the shared gate's tool set, not of any one consumer,
which is the case the shipped config exists for. Once it ships, `power-user-linux-setup`'s four
inline ignores become redundant and should be dropped at its next sweep.

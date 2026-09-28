---
status: blocked on actionlint and act accepting the self-repository uses form, checked at every consumer sweep
updated: 2026-09-28
---

# Two things this repo is waiting on upstream actionlint and act for

## Context

Both are workarounds whose removal nothing will prompt. Nothing fails when the upstream fix lands:
the workaround simply keeps working, in this repo and in every consumer that pulls the shipped
configs. So this plan is the trigger. `contributing/consumer-sweep.md` points here, so every sweep
re-runs the checks below.

[DEFERRED: **re-enable zizmor's `self-repository` audit** once both actionlint and act accept
GitHub's self-repository form, `uses: $/...` (announced 2026-07-30). It is disabled in the shipped
`src/repo_tasks/configs/zizmor.yml`, whose comment carries the reasoning, because the gate's other
two readers of the same files reject the fix: actionlint's `rule_workflow_call.go` accepts only
`./path` or `owner/repo/path@ref`, and act's `Job.Type()` in `pkg/model/workflow.go` returns
`JobTypeInvalid` for anything not starting `./`. Checked 2026-09-28 against actionlint
`main@011a6d1` (last commit 2026-04-19) and the act clone in `$RESEARCH_HOME`. Decided in the
retired `plans/2026-09-28-zizmor-self-repository-audit-conflicts-with-actionlint-and-act.md`.]

[DEFERRED: **actionlint does not know the `ubuntu-26.04` runner label.** Naming it in `runs-on:`
fails the gate with `[runner-label]` unless a `.github/actionlint.yaml` declares it. Nothing here
names it today, because Linux jobs float on `ubuntu-latest` (`contributing/quality-gate.md`,
"Workflow hardening"). This only matters if a pin or a test-ahead job is ever wanted, but it is the
same upstream, so the same check covers it. Checked 2026-09-28 against the same actionlint commit.]

## The checks

Refresh first, since the library clones are snapshots:

```shell
python3 ~/.agents/skills/research-library/scripts/library.py update
```

Then, for actionlint, **behaviour rather than source**. Source can be restructured, but a workflow
either lints or it does not:

```shell
mkdir -p /tmp/aprobe/.github/workflows
printf 'on: push\njobs:\n  a:\n    uses: $/.github/workflows/b.yml\n  c:\n    runs-on: ubuntu-26.04\n    steps:\n      - run: "true"\n' > /tmp/aprobe/.github/workflows/a.yml
uvx --from actionlint-py actionlint /tmp/aprobe/.github/workflows/a.yml
```

Read the two errors separately: one line per wait, `reusable workflow call "$/..."` and
`label "ubuntu-26.04" is unknown`. A missing line means that wait is over for actionlint. `uvx`
takes the latest release of the PyPI wrapper, which is what a consumer's lock would move to.

For act, source is what there is. act has no lint mode that stops before Docker:

```shell
rg -n 'HasPrefix\(j\.Uses, "\./"\)|\$/' $RESEARCH_HOME/repos/github.com--nektos--act/pkg/model/workflow.go
```

A `$/` branch next to the `./` one in `Job.Type()` means act accepts it.

## Recommended direction

When **both** tools accept `$/`:

1. Remove the `self-repository` block from `src/repo_tasks/configs/zizmor.yml`.
2. Run `inv configs.pull`.
3. Rewrite this repo's `uses: ./.github/workflows/security-reusable.yml` in `security.yml` to `$/`.
4. Run the gate and `inv test.workflows`, the latter because act is the reader most likely to
   disagree.

The change then reaches consumers through the normal release and sweep, and each one rewrites its
own `uses: ./` lines. Retire the first `DEFERRED` then.

When actionlint knows `ubuntu-26.04`, close the second `DEFERRED`, with no action beyond that.
Retire the plan once both are closed.

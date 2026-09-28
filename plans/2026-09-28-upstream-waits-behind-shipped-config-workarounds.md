---
status: blocked on actionlint, act and invoke fixing what three shipped-config workarounds cover, checked at every consumer sweep
updated: 2026-09-29
---

# Workarounds in the shipped configs that wait on an upstream fix

## Context

Each is a workaround whose removal nothing will prompt. Nothing fails when the upstream fix lands:
the workaround simply keeps working, in this repo and in every consumer that pulls the shipped
configs. So this plan is the trigger. `contributing/consumer-sweep.md` points here, so every sweep
re-runs the checks below. Two wait on actionlint and act, which is what this plan was first filed
for; the third, on invoke, moved here 2026-09-29 from the retired
`plans/2026-08-29-pytest-ini-anyio-mode.md`, where it had no trigger at all.

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

[DEFERRED: **drop `ignore:unclosed file:ResourceWarning` from the shipped `pytest.ini`** once
`invoke` closes the subprocess pipes its `Local` runner opens. The comment beside the line names the
condition. On `pyinvoke/invoke` `main@6a71e68`, `Local.start` opens `stdout`/`stderr`/`stdin` as
pipes (`invoke/runners.py:1363`) and `Local.stop` (`:1420`) closes only `self.parent_fd`, and only
on the PTY path, so the two read pipes are closed by nothing — unmet upstream, not merely
unreleased. Re-checked 2026-09-29: invoke 3.0.3 is still the latest release, with no push in 174
days, and the probe below still prints two `unclosed file` lines.]

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

For invoke, a release number and a probe that measures the invoke actually installed, since "is
there a newer release" alone answers nothing while the fix is unmet upstream:

```shell
python3 ~/.agents/skills/research-library/scripts/package_health.py pypi invoke
python -W error::ResourceWarning -c "import gc; from invoke import Context; Context().run('true', hide=True); gc.collect()"
```

The probe prints two `unclosed file` lines while the leak remains. When it prints nothing, the
ignore can go.

[PITFALL: the probe reports the warnings but **exits 0**, because they are raised during
finalization, where `-W error` cannot turn them into a failure. Reading the exit code rather than
the output says "fixed" about a version that still leaks.]

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

When the invoke probe prints nothing, remove the `ResourceWarning` ignore and its comment from
`src/repo_tasks/configs/pytest.ini`, run `inv configs.pull` and the gate, and close the third.

Retire the plan once all three are closed.

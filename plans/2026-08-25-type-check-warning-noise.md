---
status: idea
updated: 2026-08-25
---

# `quality.type-check` emits thousands of warnings on a green run

## Context

A passing `inv quality.precommit` prints ~1 MB of basedpyright warnings and 0 errors — measured
2026-08-25 with the shared `pyrightconfig.json` (`recommended` mode, `failOnWarnings: false`):

| repo                     | total | code side                 | tests side          |
| ------------------------ | ----: | ------------------------- | ------------------- |
| `repo-tasks`             | 2,414 | `src/` 709, `tasks.py` 24 | `tests/` 1,681      |
| `power-user-linux-setup` | 4,144 | `tasks/` 2,405            | `tests/unit/` 1,739 |

None of it gates anything; it is output nobody reads. The cost is on agents: every session working
in a consumer repo either pipes the gate through `| tail` (masking the exit code — the failure
`~/AGENTS.md`'s "Reading a command's result" rule exists for) or redirects it to a log and reads
that back, and the `~/AGENTS.md` Bash rules had to be rewritten twice in two days around that habit.
The habit is rational while the output is 1 MB; the wording fix in `power-user-linux-setup`
(`contributing/global-agents-md.md`, "Composing a Bash call", 2026-08-25) says so and points here.

### Where the noise actually comes from (measured 2026-08-25, `--outputjson`)

The `Unknown*` + `MissingParameterType` family is ~85% of both repos. It is **not** invoke leaking
through `allowedUntypedLibraries` — three separate causes, each with a different fix:

1. **Our own task code never annotates `c`.** Zero `def f(c: Context` signatures exist in
   `src/repo_tasks/` or `power-user-linux-setup/tasks/`. `allowedUntypedLibraries: ["invoke"]` is
   moot twice over: invoke ≥2 ships `py.typed` with a typed `Context.run(...) -> Result`, and the
   setting only acts on names _imported from_ invoke — an unannotated `c` is never associated with
   invoke at all, so `c.run`, `.stdout`, `.ok`, `.strip()` are all "Type of X is unknown" and every
   argument built from them cascades. Experiment: adding `c: Context` to the 15 functions in
   `quality.py` and nothing else took that file from 75 warnings to 21 (all `Unknown*` and
   `MissingParameterType` gone: 15+10+15+18+9 → 0+0+0+0+1). The residue is genuine signal (see 3).
2. **Tests never annotate fixtures.** `monkeypatch`, `tmp_path`, `capsys`, `tmp_cwd`, and the `c`
   handed to every test are all bare, so `monkeypatch.setattr` (146× in power-user-linux-setup
   alone), `capsys.readouterr().out`, `tmp_path.write_text` are all Unknown. Annotating `c` in
   `src/` helps tests only marginally (`test_quality.py` 48 → 43) because of 3.
3. **Two invoke typing gaps that are upstream's, not ours** (verified against `invoke` 3.0.3 and
   current `main`):
   - `def task(*args: Any, **kwargs: Any) -> Callable` — bare `Callable` means
     `Callable[..., Unknown]`, so `@task` erases the decorated function's type. That is every
     `reportUntypedFunctionDecorator` hit (27 in `src/`) and the reason tests see
     `quality.build`/`dist.list_versions` as "partially unknown" no matter how the test is written.
   - `invoke/__init__.py` re-exports with `# noqa` imports, no `__all__` and no `import X as X`;
     under `py.typed` that makes `from invoke import task, Context, Result, MockContext, Exit` a
     `reportPrivateImportUsage` (50 in this repo). Importing from the defining submodule
     (`invoke.tasks`, `invoke.context`, `invoke.runners`, `invoke.exceptions`) sidesteps it.

The remaining rules are small and mostly legitimate once the above is fixed:
`reportUnusedCallResult` (a `c.run(...)` whose `Result` is dropped — idiomatic invoke, 11 in
`quality.py` alone after annotation), `reportUnusedParameter` (`c` on composite tasks with an empty
body), `reportPrivateUsage` (tests importing `_helpers`, 150 in power-user-linux-setup — a
deliberate test convention there), `reportMissingTypeArgument` (109 in
`power-user-linux-setup/tasks/`, real).

### How other projects handle this (prior art, 2026-08-25)

- **Per-directory strictness is the standard answer.** mypy's documented pattern is strict globally
  with `[mypy-tests.*] disallow_untyped_defs = false` (its "existing codebase" guide and Wolt's
  "professional-grade mypy configuration"). Pyright has the same shape via `executionEnvironments` —
  "any of the type check diagnostics settings" can be overridden per root, which is what our `tests`
  environment already does for `reportUnusedFunction`. What pyright does _not_ offer is a
  per-environment `typeCheckingMode` (microsoft/pyright#8263 rejected; DetachHead/basedpyright#1638
  open, PR #1639 unmerged) — the `strict` array only upgrades. So "lenient tests" has to be spelled
  as an explicit per-rule list, not a mode name.
- **Eric Traut (pyright maintainer) on `reportUnknown*`:** "If you are using libraries that are
  untyped or partially typed, I recommend against using the `reportUnknown...` strict-mode
  diagnostic rules" (microsoft/pyright discussion #6243); the alternative he offers is a local stub
  for the offending library. Given cause 3, that is exactly our situation for `@task`.
- **basedpyright baseline** (`--writebaseline` → `.basedpyright/baseline.json`) is built for
  silencing a known backlog while keeping new code strict; its own docs scope it to adopting
  stricter rules on old code. Rejected here: it freezes ~2,400 diagnostics per repo as a committed
  file that must be regenerated whenever unrelated code moves, and hides the fact that the fix is a
  few hundred annotations.
- **CLI `--level error`** exists and would make a green run print only the summary line without
  changing what is checked. It is a presentation fix only — the warnings stay invisible in CI and in
  every consumer, which is the same "output nobody reads" in a smaller font.

## Recommended direction

Tiered by what the code is, not one global relaxation — strictness in `src/` stays, and the noise is
removed by making the code satisfy it where cheap and by scoping the rules where they don't apply.

### Tier 1 — `src/` and `tasks/` (production task code): keep every rule, fix the code

- Annotate `c: Context` on every task and helper (the one change that removes ~90% of the tier's
  warnings, per the `quality.py` experiment). Type the remaining parameters while there
  (`bump: str`, `push: bool = False`, `group: str | None = None`); invoke maps annotations to CLI
  flag types, so this is the correct declaration anyway. Import from
  `invoke.context`/`invoke.tasks`/... to clear `reportPrivateImportUsage` without touching the rule.
- Ship a partial stub for `invoke.tasks.task` so `@task` preserves the wrapped signature (`stubPath`
  `typings/invoke/tasks.pyi` with a `ParamSpec` overload; basedpyright merges partial stubs). This
  clears `reportUntypedFunctionDecorator` in `src/` _and_ the "partially unknown" cascade in tests,
  and is what Traut recommends over disabling `reportUnknown*`. Offer it upstream to pyinvoke as
  well (`task() -> Callable[[Callable[P, R]], Task[Callable[P, R]]]`, plus `__all__` in
  `__init__.py`).
- [DECISION: `reportUnusedCallResult` is `none` family-wide (2026-08-25, landed in the shared
  `pyrightconfig.json` with the rationale as a comment). A dropped `c.run()` `Result` is the invoke
  idiom, `_ = c.run(...)` everywhere is churn with no bug class behind it, ruff B018 covers the
  bare-expression case, and pyright's own `strict` leaves the rule off — only basedpyright
  `recommended` turns it on.]

### Tier 2 — `tests/` (this repo's and every consumer's): keep the bug-finding rules, drop the annotation-discipline rules

Extend the existing `executionEnvironments[root=tests]` override — same mechanism, same file, no new
concept. Keep everything that finds real bugs in tests (`reportAny`, `reportUnreachable`,
`reportUnusedImport`/`Variable`, `reportUnnecessary*`, `reportMatchNotExhaustive`, ...). Set to
`none` the rules that only measure annotation completeness or enforce API conventions tests
legitimately violate:

- `reportMissingParameterType`, `reportUnknownParameterType`, `reportUnknownArgumentType`,
  `reportUnknownVariableType`, `reportUnknownMemberType`, `reportUnknownLambdaType` — the mypy
  `allow_untyped_defs`-for-tests equivalent.
- `reportPrivateUsage` — tests importing `_private` helpers is the family's convention.
- `reportUnusedParameter` — a fixture requested for its side effect (`tmp_cwd`) is "not accessed" by
  design.

Annotating built-in fixtures (`monkeypatch: pytest.MonkeyPatch`, `tmp_path: Path`, and pytest's
`CaptureFixture[str]` for `capsys`) stays _encouraged_ — it gives real completion and catches misuse
— but not _required_, which is the tier boundary.

[DECISION: `reportUnknownMemberType` is in the tests-tier `none` list (2026-08-25) — Tier 1 types
the helpers tests call, so keeping it there would only re-impose fixture-annotation discipline on
every consumer's tests.]

### Tier 3 — test fixture repos (`tests/fixtures/*`, the gitflow twin, scaffold outputs)

Already outside `include` (`src*`/`tests*`/`tasks*` are top-level-anchored). Nothing to do; keep it
that way rather than adding an `exclude`.

### Presentation

After tiers 1–2 a green run should be near zero warnings on its own. Then, and only then, decide
whether `quality.type-check` also passes `--level error` (or switches `failOnWarnings` on) — the
acceptance test is unchanged: `inv quality.precommit` on a clean tree in `power-user-linux-setup`
fits in a Bash tool result untruncated.

## Open questions

- [NEEDS CLARIFICATION: where the `@task` stub lives. (a) `typings/invoke/` materialized into each
  consumer's root by `configs.ensure` from a canonical copy in `src/repo_tasks/configs/` — pyright's
  default `stubPath`, visible in the consumer tree, same mechanism as `ruff.toml`. (b) A PEP 561
  `invoke-stubs` distribution (partial, `py.typed` = `partial`) in the `repo-tasks-quality` group —
  zero files in consumers and reusable by anyone, but a second thing to version and publish
  (typeshed's `types-invoke` was retired when invoke went inline, so the name is free). Pyright's
  resolution order (`stubPath` → `-stubs` packages → inline `py.typed`) makes either work; (a) as
  the pilot, (b) once it has proven out, is the recommendation.]
- [NEEDS CLARIFICATION: after Tier 1 lands, flip `failOnWarnings` to `true` so the count can't
  regress silently, with the remaining warnings fixed or explicitly downgraded first?]

[DEFERRED: `power-user-linux-setup/tasks/allowlist.py` alone carries 580 warnings and 109
`reportMissingTypeArgument` across `tasks/` — a real typing pass for that repo, sequenced after the
shared config change lands there via `configs.ensure`.]

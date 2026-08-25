---
status: in-progress
updated: 2026-08-25
depends_on: [power-user-linux-setup]
---

# `quality.type-check` emits thousands of warnings on a green run

## Context

A passing `inv quality.precommit` printed ~1 MB of basedpyright warnings and 0 errors — measured
2026-08-25 with the shared `pyrightconfig.json` (`recommended` mode, `failOnWarnings: false`):

| repo                     | total | code side                 | tests side          |
| ------------------------ | ----: | ------------------------- | ------------------- |
| `repo-tasks`             | 2,414 | `src/` 709, `tasks.py` 24 | `tests/` 1,681      |
| `power-user-linux-setup` | 4,144 | `tasks/` 2,405            | `tests/unit/` 1,739 |

None of it gated anything; it was output nobody read. The cost was on agents: every session working
in a consumer repo either piped the gate through `| tail` (masking the exit code — the failure
`~/AGENTS.md`'s "Reading a command's result" rule exists for) or redirected it to a log and read
that back, and the `~/AGENTS.md` Bash rules had to be rewritten twice in two days around that habit.
The habit was rational while the output was 1 MB; the wording fix in `power-user-linux-setup`
(`contributing/global-agents-md.md`, "Composing a Bash call", 2026-08-25) says so and points here.

### Where the noise actually came from (measured 2026-08-25, `--outputjson`)

The `Unknown*` + `MissingParameterType` family was ~85% of both repos. It was **not** invoke leaking
through `allowedUntypedLibraries` — three separate causes, each with a different fix:

1. **Our own task code never annotated `c`.** Zero `def f(c: Context` signatures existed in
   `src/repo_tasks/` or `power-user-linux-setup/tasks/`. `allowedUntypedLibraries: ["invoke"]` is
   moot twice over: invoke ≥2 ships `py.typed` with a typed `Context.run(...) -> Result`, and the
   setting only acts on names _imported from_ invoke — an unannotated `c` is never associated with
   invoke at all, so `c.run`, `.stdout`, `.ok`, `.strip()` were all "Type of X is unknown" and every
   argument built from them cascaded. Experiment: adding `c: Context` to the 15 functions in
   `quality.py` and nothing else took that file from 75 warnings to 21.
2. **Tests never annotate fixtures.** `monkeypatch`, `tmp_path`, `capsys`, `tmp_cwd`, and the `c`
   handed to every test are all bare, so `monkeypatch.setattr` (146× in power-user-linux-setup
   alone), `capsys.readouterr().out`, `tmp_path.write_text` were all Unknown.
3. **Two invoke typing gaps that are upstream's, not ours** (verified against `invoke` 3.0.3 and
   current `main`):
   - `def task(*args: Any, **kwargs: Any) -> Callable` — bare `Callable` means
     `Callable[..., Unknown]`, so `@task` erases the decorated function's type. That was every
     `reportUntypedFunctionDecorator` hit (27 in `src/`) and the reason tests saw
     `quality.build`/`dist.list_versions` as "partially unknown" no matter how the test was written
     — and why 168 tests carried `# pyright: ignore[reportAny, reportFunctionMemberAccess]` on every
     `task.body(...)` call.
   - `invoke/__init__.py` re-exports with `# noqa` imports, no `__all__` and no `import X as X`;
     under `py.typed` that makes `from invoke import task, Context, Result, MockContext, Exit` a
     `reportPrivateImportUsage` (50 in this repo). Importing from the defining submodule
     (`invoke.tasks`, `invoke.context`, `invoke.runners`, `invoke.exceptions`) sidesteps it.

### How other projects handle this (prior art, 2026-08-25)

- **Per-directory strictness is the standard answer.** mypy's documented pattern is strict globally
  with `[mypy-tests.*] disallow_untyped_defs = false` (its "existing codebase" guide and Wolt's
  "professional-grade mypy configuration"). Pyright has the same shape via `executionEnvironments` —
  "any of the type check diagnostics settings" can be overridden per root, which is what our `tests`
  environment already did for `reportUnusedFunction`. What pyright does _not_ offer is a
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

## Design

Tiered by what the code is, not one global relaxation — strictness in `src/` stays, and the noise is
removed by making the code satisfy it where cheap and by scoping the rules where they don't apply.
Landed in `repo-tasks` 2026-08-25: **2,414 → 1 warning, 0 errors** on the same rule set.

### 1. Tier 1 — `src/` and `tasks/` (production task code): keep every rule, fix the code

- Every task and helper annotates `c: Context` and its remaining parameters (`bump: str`,
  `push: bool = False`, `group: str | None = None`). invoke maps annotations to CLI flag types, so
  this is the correct declaration anyway.
- Imports come from the defining submodule (`invoke.context`, `invoke.tasks`, `invoke.collection`,
  `invoke.exceptions`, `invoke.runners`, `invoke.program`, `invoke.config`), clearing
  `reportPrivateImportUsage` without touching the rule.
- Cross-module use of an underscored helper (`deps.py` → `gitflow._next_steps`, `gitflow.py` →
  `version._bump`, `tasks.py` → `configs._CONFIG_FILES`) keeps the underscore — it marks "not a
  task, stays out of the CLI namespace", not "private to the module" — with a one-line
  `# pyright: ignore[reportPrivateUsage]` saying so at the import.
- [DECISION: `reportUnusedCallResult` is `none` family-wide (2026-08-25, in the shared
  `pyrightconfig.json` with the rationale as a comment). A dropped `c.run()` `Result` is the invoke
  idiom, `_ = c.run(...)` everywhere is churn with no bug class behind it, ruff B018 covers the
  bare-expression case, and pyright's own `strict` leaves the rule off — only basedpyright
  `recommended` turns it on.]
- [DECISION: `reportUnusedParameter` is `hint` family-wide (2026-08-25) — pyright's own `strict`
  level; `recommended` raises it to a warning. invoke's task protocol hands every task a `Context`
  first whether or not the body uses it (a composite task whose whole body is its `pre=[...]` list,
  a discover function keeping `c` for symmetry with its siblings), so at warning level it fires on
  the structure, not on a mistake. `hint` keeps it in the editor and out of the CLI.]

### 2. The `@task` stub — `typings/invoke/tasks.pyi`

A partial stub overriding only `invoke.tasks`: `Task[T]` generic with
`__call__(self: Task[Callable[P, R]], *args: P.args, **kwargs: P.kwargs) -> R`, and `task()` as two
`ParamSpec` overloads (bare `@task` and `@task(pre, ...)`) returning `Task[Callable[P, R]]`. Every
other invoke module keeps its inline types — pyright's resolution order is `stubPath` (default
`./typings`) → `-stubs` packages → inline `py.typed`, and a lone `tasks.pyi` in `typings/invoke/`
with no `__init__.pyi` merges cleanly with the installed package (verified: `Context` imported from
`invoke.context` still resolves inline; `reportUntypedFunctionDecorator` 27 → 0; the 168
`task.body(...)` ignore comments in tests became `reportUnnecessaryTypeIgnoreComment` errors and
were deleted).

Two deliberate narrowings, commented in the stub: `Task.pre`/`.post` attributes are
`list[Task[Any] | Call]` (no `str`) because that is what every `pre=[...]` in this family holds, and
`Call` answers `.name` through its `__getattr__`.

- [UNVERIFIED: whether a stub file in `stubPath` also reaches `from invoke import task` — that path
  goes through the inline `invoke/__init__.py`, whose own `from .tasks import task` may resolve to
  the inline `tasks.py` rather than the stub. The pilot switched to submodule imports in the same
  change, so the two were never separated; matters for consumers that keep `from invoke import`.]
- [DEFERRED: shipping the stub to consumers. Pilot only, local to `repo-tasks` for now. Options when
  it has proven out: (a) `typings/invoke/` materialized into each consumer's root by
  `configs.ensure` from a canonical copy in `src/repo_tasks/configs/` — same mechanism as
  `ruff.toml`, visible in the consumer tree; (b) a PEP 561 `invoke-stubs` distribution (partial,
  `py.typed` = `partial`) in the `repo-tasks-quality` group — zero files in consumers and reusable
  by anyone, but a second thing to version and publish (typeshed's `types-invoke` was retired when
  invoke went inline, so the name is free). Until one lands, a consumer running `configs.pull` gets
  the tier-2 config but not the stub, so its `@task` sites still warn.]
- [DEFERRED: offer the signature upstream to pyinvoke — the stub's `ParamSpec` overloads for
  `task()` plus `__all__` in `__init__.py`. `main` is unchanged as of 2026-08-25. Delete the local
  stub once a released invoke carries it.]

### 3. Tier 2 — `tests/`: keep the bug-finding rules, drop the annotation-discipline rules

The existing `executionEnvironments[root=tests]` override, extended — same mechanism, same file, no
new concept. Everything that finds a real bug in a test stays on (`reportAny`, `reportUnreachable`,
`reportUnusedImport`/`Variable`, `reportUnnecessary*`, `reportMatchNotExhaustive`, ...). Set to
`none`: `reportMissingParameterType`, `reportUnknownParameterType`, `reportUnknownArgumentType`,
`reportUnknownVariableType`, `reportUnknownMemberType`, `reportUnknownLambdaType` (the mypy
`allow_untyped_defs`-for-tests equivalent) and `reportPrivateUsage` (tests reach into `_helpers` by
convention — 47 more `# pyright: ignore[reportPrivateUsage]` comments became unnecessary and were
deleted).

Annotating built-in fixtures (`monkeypatch: pytest.MonkeyPatch`, `tmp_path: Path`, pytest's
`CaptureFixture[str]` for `capsys`) stays _encouraged_ — it gives real completion and catches misuse
— but not _required_, which is the tier boundary.

- [DECISION: `reportUnknownMemberType` is in the tests-tier `none` list (2026-08-25) — Tier 1 types
  the helpers tests call, so keeping it would only re-impose fixture-annotation discipline on every
  consumer's tests.]
- [PITFALL: typing `c` in `src/` surfaced four tests passing `None` as the context
  (`discover_*(None)` in `test_dogfood_sample_service.py`) — harmless at runtime because those
  discover functions ignore `c`, but a type error the moment the parameter was declared. Fixed to
  pass a real `Context`; expect the same in any consumer that annotates.]

### 4. Tier 3 — fixture projects under `tests/`

`include: ["tests*"]` is recursive, so `tests/fixtures/sample-service/` **is** checked, under the
tests tier (an earlier draft of this plan claimed otherwise). That is fine — it is real code and the
one remaining warning (`reportImplicitOverride` on its `log_message`) is a real finding — but it is
checked as _this_ repo's tests, not as its own project with its own config.

- [DEFERRED: the sample-service `reportImplicitOverride` warning. `typing.override` is 3.12+ and the
  fixture declares `>=3.11` with no dependencies; either raise its floor or accept the one line. Not
  worth an `exclude` — the config's own comment explains why an exclude list is the wrong shape.]

### 5. Presentation

With tiers 1–3 a green run prints the summary line and one warning. `--level error` /
`failOnWarnings` are no longer needed to make the output fit; the acceptance test is now met by the
code rather than by hiding output.

- [DEFERRED: flip `failOnWarnings` to `true` once `power-user-linux-setup` is also at ~0, so the
  count can't silently climb back. Blocked on the rollout below.]

## Files touched

- `typings/invoke/tasks.pyi` — new partial stub (§2).
- `src/repo_tasks/*.py`, `tasks.py` — `c: Context` + parameter annotations, submodule imports, three
  documented `reportPrivateUsage` ignores, `configs._own_pyproject_data` typed as
  `dict[str, object]` (§1).
- `pyrightconfig.json` + `src/repo_tasks/configs/pyrightconfig.json` (byte-identical) —
  `reportUnusedCallResult: none`, `reportUnusedParameter: hint`, tests-tier rule list (§1, §3).
- `tests/**/*.py` — 215 now-unnecessary `# pyright: ignore` rules removed, submodule imports,
  `test_dogfood_sample_service.py` passes a real `Context` (§3).

## Verification

- `inv quality.precommit` on a clean tree: `0 errors, 1 warning, 0 notes`, 223 unit tests pass,
  output fits in one Bash tool result (2026-08-25).
- The stub is exercised, not just present: `reportUnnecessaryTypeIgnoreComment` fired on every
  `task.body(...)` ignore in tests once the stub resolved, which is the type checker confirming
  `Task.body` is now typed.

## Rollout

- [DEFERRED: `power-user-linux-setup` — `configs.pull` for the tier-2 config, then the same
  annotation pass over `tasks/` (`c: Context`, parameters, submodule imports). Its own residue after
  that is real: `tasks/allowlist.py` alone carried 580 warnings and `reportMissingTypeArgument` ×109
  across `tasks/`. Sequenced after the stub-shipping decision (§2) so the pass is done once.]
- [UNVERIFIED: no other consumer's test suite depends on the `reportPrivateUsage` warning-as-error
  behavior or on `from invoke import ...` re-exports being tolerated — `scaffoldapy`'s template
  `tasks.py` imports `from repo_tasks import ns` only, so it should be unaffected; check its
  generated output once the config ships.]

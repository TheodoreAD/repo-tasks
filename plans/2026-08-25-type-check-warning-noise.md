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
     (`invoke.tasks`, `invoke.context`, ...) sidesteps it at the cost of the idiomatic form every
     invoke tutorial uses; a stub `__init__.pyi` in the `as X` form fixes it outright (§2).

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
- Imports stay the idiomatic `from invoke import Context, task, ...` — `invoke-stubs` (§2) is what
  makes those names public to the checker. (The pilot briefly moved every import to the defining
  submodule to dodge `reportPrivateImportUsage`; reverted once the stub package landed.)
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

### 2. The `@task` stub — the `invoke-stubs` distribution

<https://github.com/TheodoreAD/invoke-stubs>, a PEP 561 partial stub package (`py.typed` =
`partial`) in the `repo-tasks-quality` group as a git direct reference, the same way consumers
install `repo-tasks` itself. It overrides only `invoke.tasks` — `Task[T]` generic with
`__call__(self: Task[Callable[P, R]], *args: P.args, **kwargs: P.kwargs) -> R`, and `task()` as two
`ParamSpec` overloads (bare `@task` and `@task(pre, ...)`) returning `Task[Callable[P, R]]` — plus a
package `__init__.pyi` that re-exports invoke's public names in the `import X as X` form. Every
other invoke module keeps its inline types (pyright's resolution order is `stubPath` → `-stubs`
packages → inline `py.typed`, and a partial `-stubs` package falls through per module). Verified
here: `reportUntypedFunctionDecorator` 27 → 0, `reportPrivateImportUsage` 50 → 0 with the idiomatic
`from invoke import ...` restored everywhere, and the 168 `task.body(...)` ignore comments in tests
became `reportUnnecessaryTypeIgnoreComment` errors and were deleted. Pilot history: a `stubPath`
copy (`typings/invoke/tasks.pyi`) landed first and was removed once the package existed.

Two deliberate narrowings, commented in the stub: `Task.pre`/`.post` attributes are
`list[Task[Any] | Call]` (no `str`) because that is what every `pre=[...]` in this family holds, and
`Call` answers `.name` through its `__getattr__`.

- [PITFALL: a `stubPath` stub for one submodule does not reach `from invoke import task`. That path
  goes through the inline `invoke/__init__.py`, whose own `from .tasks import task` resolves to the
  inline `tasks.py`; a probe (2026-08-25) shows the decorated function as `(...) -> Unknown` and
  `task` as invoke's inline `(...) -> ((...) -> Unknown)`. Only `from invoke.tasks import task`
  picks up the stub. Adding a `typings/invoke/__init__.pyi` with `as`-form re-exports does not fix
  it either: `stubPath` has no partial-package semantics, so the moment the stub directory has an
  `__init__.pyi` it shadows the whole package and every un-stubbed sibling (`.context`, `.runners`)
  becomes `"Context" is unknown import symbol` (probe, 2026-08-25).]
- [DECISION: the stub ships as a PEP 561 partial stub distribution (`invoke-stubs`, `py.typed`
  containing `partial`), not via `stubPath`. Verified 2026-08-25 with a throwaway `invoke-stubs/`
  dropped into this venv's site-packages: `from invoke import Context, MockContext, Result, task` —
  the idiomatic form every invoke tutorial uses — resolves with no `reportPrivateImportUsage`, the
  decorated task as `Task[(c: Context, name: str) -> int]`, and `Context.run`/`MockContext` falling
  through to invoke's inline types. That is the one mechanism that gives consumers the idiomatic
  import back _and_ clears the `__init__` re-export warning, because the stub's own `__init__.pyi`
  uses the `as X` form invoke's doesn't. `stubPath` is fine for the pilot but forces every consumer
  onto `from invoke.tasks import task`. (typeshed's `types-invoke` was retired when invoke went
  inline, so the name is free.)]
- [DECISION: `invoke-stubs` is its own repo, git-sourced, not a subdirectory here and not (yet) on
  PyPI (2026-08-25). Keeps `repo-tasks` single-purpose, and the git direct reference is the shape
  consumers already use for `repo-tasks` itself; a push to that repo's `main` is a release, so its
  `version` bumps on every stub change. `ensure_deps` splices the entry into consumers unchanged —
  `_bare_name` reads `invoke-stubs` off the `@ git+` spec — so every consumer gets it on its next
  `configs.ensure-deps`. PyPI remains an option via `plans/2026-08-22-pypi-publish-integration.md`
  if the package is ever worth advertising.]
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

- [DECISION: `failOnWarnings: true` family-wide (2026-08-25), once both repos were at zero. The last
  warnings were structural, not defects, and each is suppressed at its one site with a comment
  rather than by lowering a rule for everyone: `src/repo_tasks/py.typed` (this package was the
  `reportMissingTypeStubs` in every consumer), a line-level ignore on the sample-service fixture's
  `log_message` (`typing.override` is 3.12+, the fixture declares 3.11 with no dependencies), and a
  file-level `# pyright: reportImportCycles=false` on `power-user-linux-setup`'s `tasks/__init__.py`
  (the Collection-building pattern the shared config's own comment describes). The rules themselves
  stay at their levels.]

## Files touched

- `pyproject.toml` — `invoke-stubs` in the `repo-tasks-quality` group (§2); the stub itself lives in
  its own repo.
- `src/repo_tasks/*.py`, `tasks.py` — `c: Context` + parameter annotations, three documented
  `reportPrivateUsage` ignores, `configs._own_pyproject_data` typed as `dict[str, object]` (§1).
- `pyrightconfig.json` + `src/repo_tasks/configs/pyrightconfig.json` (byte-identical) —
  `reportUnusedCallResult: none`, `reportUnusedParameter: hint`, tests-tier rule list (§1, §3).
- `tests/**/*.py` — 215 now-unnecessary `# pyright: ignore` rules removed,
  `test_dogfood_sample_service.py` passes a real `Context` (§3).

## Verification

- `inv quality.precommit` on a clean tree: `0 errors, 1 warning, 0 notes`, 223 unit tests pass,
  output fits in one Bash tool result (2026-08-25).
- The stub is exercised, not just present: `reportUnnecessaryTypeIgnoreComment` fired on every
  `task.body(...)` ignore in tests once the stub resolved, which is the type checker confirming
  `Task.body` is now typed.
- Same in the first consumer: `power-user-linux-setup` at `0 errors, 5 warnings`, 316 unit tests,
  gate output in one tool result (2026-08-25, see §Rollout).

## Rollout

- `power-user-linux-setup` landed 2026-08-25 (commits `c688be1`, `395dc3d`, `27a0b1f`): **4,434 → 5
  warnings, 0 errors**, 316 unit tests, gate output in one tool result. Per step: the config pull
  alone took it to 2,367 (tests/ 2,030 → 30), `invoke-stubs` to 2,287, the annotation pass to 5. Its
  residue was real, and the fix was not `dict[str, Any]` (that only trades `Unknown*` warnings for
  `reportAny` errors) but TypedDicts for every file the repo reads — setup.toml's
  `PackageConfig`/`SetupConfig` (all documented fields, `total=False`), identity.toml,
  overrides.toml, the `~/.claude/settings.json` slice it writes, and allowlist's tools/cache/rules/
  verdict shapes measured against the tracked JSON — with one `cast` at each loader
  (`util.load_toml`/`load_json` surface `object`, never `Any`). Real findings on the way, as §3
  predicted: 40 test sites passing `None` as `c`, an apt-repo `post_install` loop that would have
  iterated a string, a `KeyError` path in the archive installer, a "private" `phases._probe` used
  cross-module. The 5 left: 4 `reportImportCycles` chains (structural, see §5) and `repo_tasks`
  lacking `py.typed`.
- [PITFALL: a `total=False` TypedDict is not subscriptable — `cfg["dest"]` is
  `reportTypedDictNotRequiredAccess` (error) even where the method guarantees the key. Pyright
  narrows on `in`, including an `or`-chain (`if "dest" not in cfg or "repo" not in cfg: raise ...`),
  and that guard is a better failure than the bare `KeyError` it replaces, so
  `power-user-linux-setup` spells one per method-specific installer (`util.missing_fields`). Only
  literal keys keep their field type: `cfg.get(target)` with `target` a loop variable, even over a
  `Literal[...]`-typed tuple, resolves to `Any` — spell the lookups out per field instead.]
- [PITFALL: an editable install resolved through a `.pth` (uv/hatch) makes pyright treat the
  project's own package as a _library_ — every test file importing `tasks` reported
  `reportMissingTypeStubs` (17 of the tests-tier residue). The package needs its own `py.typed`
  marker, exactly as a published one would. Same cause as the `repo_tasks` warning above.]
- [PITFALL: `configs.pull` prints "pulled" for every file even when it wrote nothing. Seen live: the
  consumer's installed `repo_tasks` was the pre-plan commit, so the first pull "pulled" the old
  config unchanged and only `uv lock --upgrade-package repo-tasks` + `uv sync` (the consumer had no
  `deps.lock`/`venv.sync` wired) made the next pull real. `configs.diff` first, or a
  "pulled"/"unchanged" distinction in the task's output, would have shown it.]
- `scaffoldapy` was **not** unaffected — corrected 2026-08-25 evening. The check above ran
  `basedpyright` on scaffoldapy's own tree; the repos it _generates_ pull `failOnWarnings: true` at
  generation, and the template's code carried twelve warnings across four files (`tasks.py`'s `ns`,
  untyped `diskcache` calls, two unannotated attributes, three implicit overrides) — all ten e2e
  combinations failed the moment the global tool reached `09321ae`. Fixed template-side in
  scaffoldapy `2e29f2b`; the lesson (a generator has two gates, and only its e2e tests the second)
  is in `plans/2026-08-25-consumer-transitions.md`.

## Migrated to

- [`contributing/type-checking.md`](../contributing/type-checking.md) — new file, and the bulk of
  it: the tiering rationale, the three root causes of the noise, why `invoke-stubs` is a separate
  PEP 561 partial-stub distribution rather than a `stubPath`, every rule level that deviates from
  `recommended` with its reasoning, the `failOnWarnings` policy, the four pitfalls (stubPath not
  reaching `from invoke import`, the `.pth`/`py.typed` trap, `None`-as-context surfaced by
  annotating, `total=False` TypedDict subscripting), and the rejected alternatives (baseline,
  `--level error`, disabling `reportUnknown*`).
- [`plans/2026-08-26-typing-followups.md`](2026-08-26-typing-followups.md) — the two `[DEFERRED:`
  items, which is what kept this file from being deletable: the upstream pyinvoke contribution and
  the `sample-service` `reportImplicitOverride` line.
- [`contributing/consumer-sweep.md`](../contributing/consumer-sweep.md) — already holds the two
  rollout pitfalls this plan surfaced (`configs.pull` printing "pulled" when it wrote nothing; a
  generator having two gates with only its e2e testing the second). Not migrated a second time —
  pointed at instead.

Deliberately **not** migrated:

- The per-repo warning counts, the step-by-step rollout narrative, and the "landed in commit X"
  entries. Verification logs — the state they describe is now just what the code is, and git history
  has the commits.
- The exact annotations added, the file lists, and `invoke-stubs`' own signatures. Code contracts,
  live in the code and in the `invoke-stubs` repo; a copy here would drift.
- The pilot history (a `typings/invoke/tasks.pyi` that landed first and was deleted once the package
  existed). Superseded detail with no reader question behind it; the surviving decision records that
  `stubPath` was rejected and why, which is the part that answers "why not just use stubPath".

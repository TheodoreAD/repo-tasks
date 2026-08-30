# Why basedpyright is configured the way it is

The shipped `pyrightconfig.json` carries most of this as inline comments — that file is the
authority on what each setting _is_. This one answers why the profile has the shape it has, what was
rejected on the way, and the traps that only showed up by hitting them.

## Strictness is tiered by what the code is, not relaxed globally

Three tiers, one config:

1. **`src/` and `tasks/`** — production task code. Every rule stays on; the code is annotated to
   satisfy it.
2. **`tests/`** — the `executionEnvironments[root=tests]` override. Every rule that finds a _bug_ in
   a test stays on (`reportAny`, `reportUnreachable`, unused import/variable, `reportUnnecessary*`,
   …). Off are the ones that only measure annotation discipline or police API conventions tests
   violate on purpose.
3. **Fixture projects under `tests/`** — `include: ["tests*"]` is recursive, so
   `tests/fixtures/sample-service/` _is_ checked, under the tests tier. It is real code and its
   findings are real; it is simply checked as this repo's tests rather than as its own project.

Annotating built-in fixtures (`monkeypatch: pytest.MonkeyPatch`, `tmp_path: Path`, pytest's
`CaptureFixture[str]` for `capsys`) stays encouraged in tests — it gives real completion and catches
misuse — but not required. That is exactly where the tier boundary sits.

Per-directory strictness is the standard answer to this problem, not a local invention: mypy's own
documented pattern for an existing codebase is strict globally with
`[mypy-tests.*] disallow_untyped_defs = false`. Pyright has the same shape via
`executionEnvironments`, with one gap — there is **no per-environment `typeCheckingMode`**
(microsoft/pyright#8263 rejected; DetachHead/basedpyright#1638 open, PR #1639 unmerged), and the
`strict` array only ever upgrades. So the tests tier has to be spelled rule by rule rather than
named as a mode.

## Where the noise came from, and why the fix was annotations

Measured 2026-08-25 with `--outputjson`: a _passing_ gate printed ~2,400 warnings in `repo-tasks`
and ~4,100 in `power-user-linux-setup`. The `Unknown*` + `MissingParameterType` family was ~85% of
both.

It was **not** invoke leaking through `allowedUntypedLibraries`. Three separate causes:

1. **Task code never annotated `c`.** `allowedUntypedLibraries: ["invoke"]` is moot twice over —
   invoke ≥2 ships `py.typed` with a typed `Context.run(...) -> Result`, and the setting only acts
   on names _imported from_ invoke, so a bare `c` is never associated with invoke at all. `c.run`,
   `.stdout`, `.ok` were all Unknown and everything built from them cascaded. Measured: adding
   `c: Context` to `quality.py`'s 15 functions and nothing else took that file 75 → 21 warnings.
   (The setting is still in the config; it is harmless, and removing it was never the fix.)
2. **Tests never annotate fixtures.** Handled by the tests tier above rather than by annotating
   every fixture in every consumer.
3. **Two upstream invoke typing gaps** — see the next section.

The lesson worth keeping: reach for annotations before reaching for a rule level. `dict[str, Any]`
is not the shortcut it looks like either — it only trades `Unknown*` warnings for `reportAny`
errors. What actually works for a file the code reads is a `TypedDict` per shape with one `cast` at
the loader.

## `invoke-stubs`, and why it is a separate distribution

Two gaps in invoke's own typing, verified against 3.0.3 and `main`:

- `def task(*args: Any, **kwargs: Any) -> Callable` — a bare `Callable` means
  `Callable[..., Unknown]`, so `@task` erases the decorated function's type. That was every
  `reportUntypedFunctionDecorator` hit, and why tests carried
  `# pyright: ignore[reportAny, reportFunctionMemberAccess]` on every `task.body(...)` call.
- `invoke/__init__.py` re-exports with `# noqa` imports, no `__all__` and no `import X as X`. Under
  `py.typed` that makes the idiomatic `from invoke import task, Context, …` a
  `reportPrivateImportUsage`.

[DECISION: the fix ships as [`invoke-stubs`](https://github.com/TheodoreAD/invoke-stubs), a PEP 561
_partial_ stub distribution (`py.typed` containing `partial`), not via `stubPath`. It overrides only
`invoke.tasks` — a generic `Task[T]` and `task()` as two `ParamSpec` overloads — plus an
`__init__.pyi` re-exporting invoke's public names in the `import X as X` form; every other invoke
module falls through to its inline types (pyright resolves `stubPath` → `-stubs` packages → inline
`py.typed`, and a partial `-stubs` package falls through per module). This is the one mechanism that
gives consumers back the idiomatic import _and_ clears the re-export warning. `stubPath` was fine
for the pilot but forces every consumer onto `from invoke.tasks import task`. Measured:
`reportUntypedFunctionDecorator` 27 → 0, `reportPrivateImportUsage` 50 → 0, and 168 now-unnecessary
ignore comments deleted. typeshed's `types-invoke` was retired when invoke went inline, so the name
was free.]

[DECISION: `invoke-stubs` is its own repo, git-sourced in the `repo-tasks-quality` group — the same
shape consumers already use for `repo-tasks` itself — rather than a subdirectory here or a PyPI
release. Keeps `repo-tasks` single-purpose; a push to that repo's `main` is a release, so its
`version` bumps on every stub change. `ensure_deps` splices the entry into consumers unchanged
(`_bare_name` reads `invoke-stubs` off the `@ git+` spec).]

[PITFALL: a `stubPath` stub for one submodule does not reach `from invoke import task`. That path
goes through the inline `invoke/__init__.py`, whose own `from .tasks import task` resolves to the
inline `tasks.py` — a probe showed the decorated function as `(...) -> Unknown`. Only
`from invoke.tasks import task` picks up such a stub. Adding a `typings/invoke/__init__.pyi` does
not fix it either: `stubPath` has no partial-package semantics, so the moment the stub directory has
an `__init__.pyi` it shadows the whole package and every un-stubbed sibling becomes
`"Context" is unknown import symbol`.]

## The rule levels that deviate from `recommended`

[DECISION: `reportUnusedCallResult` is `none` family-wide. Once `c` is typed it fires on every
`c.run(...)` whose `Result` is dropped, and dropping it is the invoke idiom — a failing command
raises `UnexpectedExit`, so the return value carries nothing a caller must consume. `_ = c.run(...)`
on most lines of every task is ceremony with no bug class behind it; the case the rule exists for (a
bare `s.strip()`) is ruff's B018. pyright's own `strict` leaves it off too — only basedpyright's
`recommended` turns it on.]

[DECISION: `reportUnusedParameter` is `hint` — pyright's own `strict` level, where `recommended`
raises it to a warning. invoke's task protocol hands every task a `Context` first whether or not the
body uses it (a composite task whose whole body is its `pre=[...]`, a discover function keeping `c`
for symmetry), so at warning level it fires on the structure, not on a mistake. `hint` keeps it in
the editor and out of the CLI.]

[DECISION: `reportUnknownMemberType` is in the tests-tier `none` list. Tier 1 types the helpers
tests call, so keeping it on would only re-impose fixture-annotation discipline on every consumer's
tests.]

[DECISION: `reportImportCycles` is downgraded to `warning`, not silenced. A package `__init__.py`
that imports every submodule to build an invoke `Collection` trips it when a submodule also does
`from . import <sibling>` — a real, standard invoke pattern. The one file that structurally trips it
carries a file-level `# pyright: reportImportCycles=false`; the rule stays live everywhere else. The
narrower fix, and the one to prefer in new code, is importing the sibling directly
(`from .sibling import name`) — see `AGENTS.md`.]

## `failOnWarnings: true`, and what it demands

[DECISION: a warning fails the run, flipped 2026-08-25 once every repo in the family was at zero.
With thousands of warnings the count was output nobody read; at zero, this is what keeps it there.
The rule it imposes: a warning that is _structural_ rather than a defect is suppressed at its one
site with a `# pyright: ignore[rule]` (or a file-level `# pyright: rule=false`) and a comment saying
why — never by lowering the rule for everyone.]

This is also why the gate's output fits in one terminal read again, which is not cosmetic: while the
output was ~1 MB, every session working in a consumer piped the gate through `| tail` or redirected
it to a log, both of which lose the exit code. `~/AGENTS.md`'s "Reading a command's result" rule
exists because of that habit, and the habit was rational while the output was that size.

[PITFALL: an editable install resolved through a `.pth` (uv/hatch) makes pyright treat the project's
own package as a _library_ — every test file importing it reports `reportMissingTypeStubs`. The
package needs its own `py.typed` marker, exactly as a published one would. `src/repo_tasks/py.typed`
exists for this reason, and it was `reportMissingTypeStubs` in every consumer until it did.]

[PITFALL: typing `c` in `src/` surfaces tests that pass `None` as the context — harmless at runtime
where the function ignores `c`, a type error the moment the parameter is declared. Four such sites
here; expect the same in any consumer that annotates. They are real findings, not noise: the same
pass turned up a loop that would have iterated a string and a `KeyError` path in an installer.]

[PITFALL: a `total=False` TypedDict is not subscriptable — `cfg["dest"]` is
`reportTypedDictNotRequiredAccess` (an error) even where the method guarantees the key. Pyright
narrows on `in`, including an `or`-chain, and that guard is a better failure than the bare
`KeyError` it replaces. Only _literal_ keys keep their field type: `cfg.get(target)` with `target` a
loop variable resolves to `Any` even over a `Literal[...]`-typed tuple — spell the lookups out per
field.]

## Rejected

- **basedpyright's baseline** (`--writebaseline` → `.basedpyright/baseline.json`). Built for
  silencing a known backlog while keeping new code strict, and its own docs scope it to adopting
  stricter rules on old code. It would have frozen ~2,400 diagnostics per repo as a committed file
  needing regeneration whenever unrelated code moved, and hidden the fact that the fix was a few
  hundred annotations.
- **`--level error`** on the CLI. A green run would print only the summary line without changing
  what is checked — the same "output nobody reads" in a smaller font, still invisible in CI and in
  every consumer.
- **Turning off the `reportUnknown*` family.** Eric Traut (pyright's maintainer) does recommend
  against those rules when working with untyped or partially-typed libraries (microsoft/pyright
  discussion #6243) — but the alternative he offers in the same breath is a local stub for the
  offending library, which is what `invoke-stubs` is. The stub was the better half of that advice.
- **`extraPaths: ["."]` in the tests execution environment**, which would permit a packaged `tests/`
  tree (`__init__.py` files, `from tests.conftest import ...`). See the decision below.

### Why `tests/` may not be a package

The tests execution environment sets `root: "tests"`, which makes `tests/` the search root for files
beneath it — so `conftest` resolves and `tests.conftest` cannot. A consumer wanting a shared test
helper imported by name across tiers meets `Import "tests.conftest" could not be resolved`, and
`extraPaths: ["."]` is the one-line fix.

[DECISION: not taken. Adding `.` to the type checker's search path also makes `src.<pkg>` resolve —
a second, blessed import route to the same code, which is precisely what a `src` layout exists to
prevent. `import src.repo_tasks.version` and `import repo_tasks.version` yield **different module
objects with separate state** at runtime, and this setting is exactly what stops the type checker
from flagging that. The cost lands in a file every consumer inherits, to buy a layout one consumer
wanted. Settled 2026-08-30.]

Measured here, four runs (basedpyright 1.39.10, this repo, two tiers):

| setup                                               | result                                             |
| --------------------------------------------------- | -------------------------------------------------- |
| `extraPaths` alone, unpackaged tree                 | 0 errors — no structural cost on the current shape |
| packaged tree, no `extraPaths`                      | `Import "tests.conftest" could not be resolved`    |
| packaged tree + `extraPaths`                        | 0 errors, all 520 tests still collected            |
| `from src.repo_tasks import version` + `extraPaths` | **resolves clean** — the reason it was rejected    |

That last row is the finding, and it is causal: the identical import is a `reportMissingImports`
error with `extraPaths` removed and nothing else changed.

The supported alternative is pytest's own: no `__init__.py`, and a shared helper imported bare
(`import conftest`), which its
[good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html) page
recommends for exactly this `src`-layout shape. The cost of that layout is the unique-basename
requirement, written down in [`test-tiers.md`](test-tiers.md) under Conftest layout.

## Rolling this out to a consumer

A generator has two gates and only its e2e tests the second: `scaffoldapy`'s own
`inv quality.precommit` says nothing about the repos it generates, which pull the shipped config at
generation time. Any "consumers verified" claim has to name which gate it ran. See
[`consumer-sweep.md`](consumer-sweep.md), which owns that procedure and the pitfalls around it.

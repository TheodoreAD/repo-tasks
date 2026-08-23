---
status: in-progress
updated: 2026-08-24
---

## Context

Two decisions taken together 2026-08-23, because they are the same change seen from two sides: what
dependency groups exist, and what `pytest` with no arguments runs.

**Direction, as given:** everything that isn't a main dependency goes in `dev`. Sub-groups inside
`dev` to control what CI installs are a thing worth having in some projects, but not here — just
main and dev. And bare `pytest` should run the unit tests, nothing else.

Today neither holds. There is a third group, `integration`, and bare `pytest` only avoids the
integration tier because `pytest.ini`'s `addopts` carries `--ignore=tests/integration`.

### Why the `integration` group exists, measured

| environment           | packages |
| --------------------- | -------- |
| default dev           | 39       |
| `--group integration` | 86       |

Per dependency, resolved standalone: `devpi-server` 43, `devpi-client` 18, `testcontainers` 10. So
it is devpi's pyramid/zope stack that doubles the environment; `testcontainers` costs **+7**
packages on top of the current dev set (`certifi`, `charset-normalizer`, `docker`, `requests`,
`urllib3`, `wrapt`, `testcontainers` — `idna`, `python-dotenv`, `typing-extensions` are already
there).

The group is per-project and never inherited, so this only ever affected contributors to this repo,
not consumers of `repo-tasks`.

### What the extra group actually cost

All three hit live while landing the dogfood sample:

- [PITFALL: `venv.sync`/`venv.create` run `uv sync --locked` with no `--group`, which _uninstalls_
  the integration group. The repo's own standard dev-loop task silently breaks the opt-in tier —
  observed as `ModuleNotFoundError: No module named 'testcontainers'` on the next integration run.]
- `tests/integration/conftest.py` imports `testcontainers` at module scope, so the whole directory
  is uncollectable without the group — including `test_version_integration.py`, which needs neither
  Docker nor devpi and whose own docstring claims it never skips.
- It is the sole reason `pyrightconfig.json` carries `"exclude": ["tests/integration"]`: those
  modules cannot import without the group. That one exclude is the root of the whole root-vs-package
  config divergence tracked in `plans/2026-08-23-configs-round-trip-divergence.md`.

## Landed 2026-08-24

Everything in Recommended direction below is implemented except §3 (where the dogfood sample lives),
which is still awaiting a call:

- Every dependency group folded into `dev`; `quality` renamed `repo-tasks-quality` and kept only
  because it is an exported manifest. `pyrightconfig.json`'s `tests/integration` exclude deleted
  with the group that caused it, which type-checked that tier for the first time and turned up two
  real defects, both fixed.
- `tests/unit/` and `tests/integration/`, three conftests, `testpaths = tests/unit`, `smoke`
  registered as a marker.
- `src/repo_tasks/testing.py` nested as `test`: `unit`/`integration`/`smoke`/`regression`/`all`,
  with only `unit` in `check`'s `pre=[...]`.

Verified against real repos, not only mocks: `test.smoke` deselects all 19 integration tests cleanly
with nothing marked yet; `test.integration` no-ops in a scratch repo with no tier; and `test.unit`
in a scratch repo with a flat `tests/` emits pytest's own warning and finds the tests. Each of the
three commits was checked out in a worktree and run against its own source, since the venv's
editable install otherwise resolves `repo_tasks` to the working tree and hides breakage.

### Sibling repos: no breakage, one latent hazard

`power-user-linux-setup` and `scaffoldapy` both declare only a `dev` group and both run
`inv quality.check` in CI, so neither the rename nor the namespace move touches them — every hit for
the old names is prose in docs and plans.

[PITFALL: both have a flat `tests/` and no `tests/unit`, so when they next run `configs.pull` they
inherit `testpaths = tests/unit` and fall back to pytest's "searching recursively from the current
directory". That works — and the warning usefully nudges toward the convention — but the fallback
search is _broader_ than `tests/`, and pytest does not respect `.gitignore`.
`power-user-linux-setup` has a gitignored `reference/` tree of vendored clones; it contains no
test-looking files today (checked), but the day one appears, that repo's default `pytest` run starts
collecting it. `norecursedirs` would bound it, at the cost of being an exclude — which the
excludes-are-brittle rule of thumb argues against. Adopting `tests/unit` in those repos removes the
question entirely and is the intended direction.]

## Open questions

[DECISION: `quality` is renamed `repo-tasks-quality` and stays included in `dev`; everything that is
only repo-tasks' own test infrastructure goes straight into `dev`. Resolved 2026-08-24.

The rename is the point. That group is not a tier — it is an **exported manifest**. `configs.py`'s
`_quality_deps()` reads it verbatim from the packaged copy of repo-tasks' own `pyproject.toml`
(force-included into the wheel as `repo_tasks/pyproject.toml`), and `configs.ensure_deps` splices
those exact entries into a _consumer's_ `dependency-groups.dev`. Its contents are public API in a
way no other group's are, and a name saying whose it is stops it reading as "the quality tier" —
which is what made folding it into `dev` look safe. Folding it would have started injecting
`testcontainers` and devpi into every scaffolded repo.

Follow-on this implies: `_quality_deps()` reads the key by name and must change with it, and its
tests pin the current name.]

[DECISION: every group folds into `dev`. Only `main` and `dev` are addressed by install/sync scripts
and tasks; a genuinely special-needs group (test matrices, ML/torch stacks) is something other
projects may need and advanced users can handle, and is explicitly not a case this repo designs for.
Resolved 2026-08-24. `repo-tasks-quality` survives as a group only because it is an exported
manifest rather than a tier, and it is included in `dev`.

Consequence, accepted rather than discovered: devpi's 43 packages land in the default environment,
taking a plain `uv sync` from 39 packages to roughly 82. Not urgent — it works, disk is not a
constraint, and `uv` is fast. Tidying it is deferred to
`plans/2026-08-24-devpi-dependency-weight.md`.]

[NEEDS CLARIFICATION: does `tests/unit/` get its own `conftest.py` immediately, or stay bare until
something needs it? The split's stated value is that the two tiers can have genuinely different
fixtures and approaches; an empty file adds a level of indirection with nothing in it yet.]

## Recommended direction

### 1. `tests/unit/` and `tests/integration/`

Move the current top-level `tests/test_*.py` into `tests/unit/`. Then bare `pytest` runs the unit
tier because that is what `testpaths` points at, not because an `--ignore` subtracts the other one.

[DECISION: `testpaths = tests/unit`, dropping `--ignore=tests/integration` from `addopts`. An
include is durable where an exclude is not — a new directory under `tests/` is picked up by an
exclude-based config the moment someone adds it, and nobody remembers to update the exclude. Same
rule of thumb applied in `plans/2026-08-19-gitignore-tool-alignment.md`.]

Consequences worth stating before doing it:

- `quality.test_integration`'s `-o addopts=...` override exists purely to strip the `--ignore`, and
  disappears with it — the new `test.integration` names its path directly, guarded by the existence
  check in §2a.
- Two `conftest.py` files, which is the real motivation: the integration one already carries
  container/index fixtures that no unit test should be able to reach by accident.
- `pyrightconfig.json`'s `include` currently names `tests`; that keeps covering both subdirectories,
  so nothing changes there.

### 2. A `test` namespace of its own

The test tasks leave the `quality` namespace entirely:

| task                          | runs                               | in `check`/`precommit`?           |
| ----------------------------- | ---------------------------------- | --------------------------------- |
| `inv test.unit`               | the unit tier                      | **yes** — the only one that is    |
| `inv test.integration`        | `tests/integration`                | no                                |
| `inv test.smoke` (later)      | `tests/integration -m smoke`       | **maybe**, deliberately undecided |
| `inv test.regression` (later) | `tests/integration -m "not smoke"` | no                                |
| `inv test.all`                | everything                         | no                                |

[DECISION: `precommit` runs the unit tier only. Smoke is the one candidate for joining it later and
stays an open call — a `precommit` that needs a Docker daemon is exactly what
`contributing/test-tiers.md`'s "the default one must stay runnable anywhere" rule exists to prevent,
and smoke tests are still integration tests.]

**Smoke** is a small set of fast integration tests giving happy-path confidence — enough to know the
system is wired up at all. **Regression** is everything else in the tier. Speed and breadth, not
subject matter.

[NEEDS CLARIFICATION: the module behind the namespace. Repo convention is one module per facility
named after what it owns, which argues for `src/repo_tasks/test.py` — but `test` is a real stdlib
package name (CPython's own test suite), so `testing.py` with an explicit
`add_collection(..., name="test")` may be the safer spelling. The namespace is `test` either way;
only the filename is in question.]

[NEEDS CLARIFICATION: `inv quality.test` disappears, which breaks any consumer naming it directly,
and this package still has no deprecation convention. Same question as the old `test` → `test-unit`
rename, now unavoidable rather than optional.]

### 2a. `testpaths` already implements the fallback — measured

The requirement was: `test.unit` should use `tests/unit` if it exists, and otherwise warn and fall
back to `tests/`, since a simple project has no split. **pytest does this itself**, so the task
needs no fallback logic at all.

With `testpaths = tests/unit` and only `tests/` present, a bare `pytest` run exits 0, runs the
tests, and emits:

```
PytestConfigWarning: No files were found in testpaths; consider removing or adjusting your
testpaths configuration. Searching recursively from the current directory instead.
```

A warning plus a fallback search — exactly the requested behaviour, from the tool rather than
hand-rolled. Measured 2026-08-24, along with the cases that constrain the design:

| case                                                  | result                                                       |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| `testpaths = tests/unit`, only `tests/` exists        | exit 0, warns, finds the tests                               |
| `testpaths = tests/unit`, both dirs exist             | exit 0, runs unit only, **zero** integration tests collected |
| `testpaths = tests/unit tests`, both exist            | wrong — collects the integration tier too                    |
| explicit `pytest tests/integration`, directory absent | **exit 4**, usage error                                      |

[DECISION: `testpaths = tests/unit` alone in the shared `pytest.ini`, and `test.unit` runs a bare
`pytest` rather than naming a path. Listing both `tests/unit tests` looks like a tidier fallback but
is wrong — with both directories present it collects the integration tier into the default run,
which is the exact thing this split exists to prevent. Naming an explicit path in the task would
also defeat the fallback, since an explicit missing path is a hard exit-4 usage error rather than a
warning.]

[DECISION: `test.integration`/`smoke`/`regression` do name their paths explicitly, so each must
check the directory exists first and print-and-return when it does not — exit 4 otherwise. Same
"No-op cleanly when an artifact kind is absent" contract as `quality.shell_check` and `helm.py`.
`test.unit` keeps the existing exit-code-5 handling on top, so a repo with no python tests at all
still passes the gate.]

### 2b. `tests/unit/conftest.py`

Worth having, and worth having early: the `MockContext`/`Result` pattern is repeated across every
`tests/test_*.py` module today, and the two tiers want genuinely different fixtures — which is the
main argument for splitting the directories at all.

[PITFALL: it is exemplary by being read, not by being distributed. This repo ships tool _config_
(`configs.pull`'s five files) and the quality dependency manifest (`configs.ensure_deps`) — it does
not ship project structure, `conftest.py`, or tests. That is `scaffoldapy`'s half of the split. A
consumer gets this pattern by looking at it, so it has to be worth reading; nothing propagates it
automatically.]

### 3. Where the dogfood sample lives

Currently `examples/sample-service`, inherited from the retired monorepo plan's schema sketch rather
than chosen. Three candidates, judged on what the thing actually is:

- **`examples/`** — reads as "here is a pattern to copy", which is not what it is. README already
  has to say it "exists to be exercised, not imitated wholesale". A name that needs that disclaimer
  is the wrong name.
- **`projects/`** — right for a monorepo that genuinely ships several services, wrong here.
  repo-tasks ships one library; a `projects/` directory at its root claims a shape it doesn't have.
  It would also set a bad precedent for scaffolded repos: nobody should create `projects/` for a
  single-project repo, least of all to hold test data.
- **`tests/fixtures/sample-service`** — what it honestly is. It exists to be built, pushed, linted,
  packaged and bumped by the integration tier, and by nothing else.

[DECISION: `tests/fixtures/sample-service`, recommended. It is a fixture — a real artifact that
exists for tests to act on — and naming it as one avoids claiming either of the two shapes above.
The retired monorepo plan independently proposed `tests/fixtures/` for exactly this kind of
workspace fixture.]

It also pays for itself twice over:

- The canonical basedpyright include list already names `tests`, and a directory include is
  recursive (measured), so the member's `src/` gets type-checked with **no change to the shared
  baseline at all**. That is `configs-round-trip-divergence.md`'s defect 2 closed for free — no new
  `examples` entry, no per-repo config, nothing pushed to consumers who have no such directory.
- It keeps `[tool.uv.workspace] members` pointed somewhere that cannot be mistaken for shipped code.

The tension worth stating: README cites this Dockerfile as the worked instance of the multi-stage
recipe, and a reference implementation living under `tests/fixtures/` reads slightly oddly. That is
acceptable — a fixture can still be the canonical worked example, and the alternative is naming the
directory after how it reads rather than what it is. If a genuinely user-facing example is ever
wanted, that is a separate artifact, most likely in `docs/`.

Move cost: `repo-tasks.toml`'s two entries, the Dockerfile's bind-mount paths, the integration
tests' path constants, and the README pointer. No code changes.

### 4. Finer granularity via marks, not directories

Smoke versus regression lives on `pytest.mark`, inside `tests/integration/` — not as two more
directories, and never as two more dependency groups. `quality.test-smoke` becomes
`pytest tests/integration -m smoke`, regression its inverse. Deliberately not designed further here;
the directory split above must not get built around a distinction it shouldn't carry.

### 5. Dependency groups

`integration` is dissolved into `dev` along with everything else, per the decision above.
`testcontainers` moving is what buys back a collectable integration directory and a
`test_version_integration.py` that runs with no group at all; devpi comes along for the ride and its
weight is deferred to `plans/2026-08-24-devpi-dependency-weight.md`.

`repo-tasks-quality` is the sole survivor as a distinct group, because it is an exported manifest
rather than a tier — see the decision under Open questions.

Sequence matters — do the group change first, then `pyrightconfig.json`'s exclude can be deleted
rather than migrated, and `configs-round-trip-divergence.md`'s defect 1 loses most of its bite.

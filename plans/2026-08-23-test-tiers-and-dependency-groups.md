---
status: idea
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

[NEEDS CLARIFICATION: "everything else in `dev`" puts devpi's 43 packages into the default
environment — a plain `uv sync` for a repo-tasks contributor goes from 39 packages to roughly 82.
That is the direct, chosen cost of "just main and dev", worth naming rather than discovering. The
alternative that keeps both the rule and the size: drop the devpi-backed tests and cover `dist.py`'s
PEP 691/503 parsing against a stub HTTP server, which is all those two tests actually need.
`contributing/test-tiers.md` records devpi being chosen deliberately over `pypiserver` because it
exercises both the JSON and HTML branches — a stub can exercise both too, and more cheaply. Worth
deciding before the group change lands: it is the difference between `dev` at 46 packages and 82.]

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

- `quality.test_integration`'s `-o addopts=...` override exists purely to strip the `--ignore`. With
  `testpaths` it becomes a plain path argument (`pytest tests/integration`), since an explicit path
  overrides `testpaths` anyway.
- Two `conftest.py` files, which is the real motivation: the integration one already carries
  container/index fixtures that no unit test should be able to reach by accident.
- `pyrightconfig.json`'s `include` currently names `tests`; that keeps covering both subdirectories,
  so nothing changes there.

### 2. One `quality.*` target per tier

The task surface follows the directory split rather than lagging behind it: a target per tier, and
the composites deliberately not running all of them.

| target                            | runs                                    | in `check`/`precommit`?                |
| --------------------------------- | --------------------------------------- | -------------------------------------- |
| `quality.test-unit`               | `tests/unit`                            | **yes** — the only test target that is |
| `quality.test-integration`        | `tests/integration`                     | no                                     |
| `quality.test-smoke` (later)      | fast integration tests, happy path only | **maybe**, deliberately undecided      |
| `quality.test-regression` (later) | everything that isn't smoke             | no                                     |

[DECISION: `precommit` runs the unit tier only. Smoke is the one candidate for joining it later, and
that stays an open call rather than something the split presumes — a `precommit` that needs a Docker
daemon is exactly what `contributing/test-tiers.md`'s "the default one must stay runnable anywhere"
rule exists to prevent, and smoke tests are still integration tests.]

Definitions worth pinning now so the marks land consistently later: **smoke** is a small set of fast
integration tests that give happy-path confidence — the thing you run to know the system is wired up
at all. **Regression** is everything else in the integration tier. The distinction is speed and
breadth, not subject matter.

Naming/compatibility notes:

- `quality.test` is the current name and is wired into `check`'s `pre=[...]`. Renaming it to
  `test-unit` is a breaking change for any consumer naming it directly, and this package has no
  deprecation convention yet. [NEEDS CLARIFICATION: rename `test` → `test-unit`, or keep `test` as
  the unit target's name and add the others alongside it? The second is non-breaking but leaves the
  least specific name on the most specific tier, which reads badly once four targets exist.]
- Whatever `check` ends up calling must keep `quality.test`'s existing exit-code-5 contract — pytest
  returns 5 when it collects nothing, and that is treated as success so a repo with no python tests
  still passes the gate. That behaviour belongs to the unit target specifically.
- `test_integration`'s `-o addopts=...` override disappears with `testpaths`; each target just names
  its own directory.

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

Move `testcontainers` into `dev` regardless of how the devpi question above lands: +7 packages buys
back a collectable integration directory, a `test_version_integration.py` that runs with no group at
all, and the removal of the one `exclude` this repo's shared config carries.

Sequence matters — do the group change first, then the `pyrightconfig.json` exclude can be deleted
rather than migrated, and `configs-round-trip-divergence.md`'s defect 1 loses most of its bite.

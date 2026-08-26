---
status: done
updated: 2026-08-27
depends_on: [power-user-linux-setup, scaffoldapy]
---

# Quality-gate coverage by concern

## What has landed

Everything needing no new dependency shipped 2026-08-26 (`f4f5252`..`e4058b1`), each with the
verification its § asked for:

| §  | landed                                                                             |
| -- | ---------------------------------------------------------------------------------- |
| 1  | `deps.audit` — found 2 real advisories on its first run                            |
| 2  | `deps.check` in the gate — proved by breaking the lock on purpose                  |
| 5  | `docs.link_check` — hand-rolled, in the gate                                       |
| 6  | `test.untested_modules` — found `cli.py` untested, now covered                     |
| 7  | `quality.verify_types` + `tests/unit/test_types.py`                                |
| 8  | `ci.status`                                                                        |
| 9  | `pytest.ini` strictness; ruff `PT`/`FURB`/`PGH`                                    |
| 11 | ci.yml permissions/concurrency/timeouts, 3.11–3.14 unit matrix; publish.yml pinned |
| 12 | `requirements.py`'s `@requires` + the derived enforcement test                     |

The four dependency-adding sections shipped 2026-08-27 (`af3ef5c`..`673c478`), each proved by making
it fail on purpose first:

| §  | landed                                                                                              |
| -- | --------------------------------------------------------------------------------------------------- |
| 3  | zizmor in `workflow_check` — 4 real workflow findings fixed first; `zizmor.yml` is a shipped config |
| 4  | `quality.dockerfile_check` (hadolint) — 4 findings, 2 fixed and 2 declined inline                   |
| 10 | `docker.check` (`docker build --check`), standalone, exercised from the integration tier            |
| 6b | `test.coverage` — pytest-cov, report only, 98% on this repo                                         |
| 13 | the autouse `no_network` fixture — `pytest-socket` later promoted to the shipped manifest           |

The consumer sweep ran the same day, against both consumers, and is written up below. The only thing
left open in this plan is §11's `deps.audit` CI step, blocked — see its `[DEFERRED:]`.

### What the implementation added beyond the design

Three things this plan did not anticipate, recorded so they are not re-derived:

- **`zizmor.yml` had to become a shipped config** (`_CONFIG_FILES`, `configs.promote`). Since zizmor
  v1.20.0 the default `unpinned-uses` policy is a blanket hash-pin, which contradicts §11's explicit
  decision to pin `publish.yml` and nothing else. The policy is expressible only in a config file
  (no CLI flag), and leaving it unshipped would have turned every consumer's gate red over a choice
  they did not make. `"*": ref-pin` is the encoding.
- **`--offline` is passed to zizmor explicitly** even though it is already the default: zizmor
  enables its online audits whenever `GH_TOKEN`/`GITHUB_TOKEN` is in the environment, which is the
  normal state inside CI. Without the flag the gate's rule set differs between a laptop and a
  runner.
- **The §12 enforcement test had a real bug**, found by `docker.check`. It keyed gate steps by bare
  function name, and `check` names a gate step (`deps.check`), the gate itself (`quality.check`) and
  now a Docker task — so it reported `docker.check` as a gate step needing Docker. Keyed on
  `(module, name)` now.

## Context

`inv quality.check` runs ruff (lint + format), dprint, basedpyright, shellcheck, shfmt, actionlint,
and the unit tier. Every one of those picks is researched and settled —
[`contributing/type-checking.md`](../contributing/type-checking.md),
[`contributing/test-tiers.md`](../contributing/test-tiers.md), and `power-user-linux-setup`'s
[`contributing/quality-tooling.md`](https://github.com/TheodoreAD/power-user-linux-setup/blob/master/contributing/quality-tooling.md)
carry the reasoning. (That last one is where the retired
`plans/2026-08-14-python-repo-scaffolding.md` §C landed; §D's config-distribution mechanism is in
that repo's `contributing/repo-family-architecture.md`.)

The complementary question had never been asked: **which classes of problem does the gate not look
for at all?** Prior research tuned the tools already chosen. This plan swept for concerns with no
tool behind them, then resolved each one.

Two rules govern every decision below, both stated by the user during the sweep:

1. **`check` stays deterministic and offline.** Anything whose result can change without a code
   change — a vulnerability database, an external URL — or that pulls a Docker image or a binary at
   run time, is a standalone task, never a gate step.
2. **A task that is not in the gate must declare what it pulls**, so the CI-integration hurdle and
   the risk are visible without reading the body.

Everything in `check` ships to every consumer through `repo-tasks-quality`, so each addition is a
dependency added to `power-user-linux-setup`, `scaffoldapy`, and every generated repo — see
[`contributing/consumer-sweep.md`](../contributing/consumer-sweep.md).

Tool selection below started from package metadata, project docs, and 2026 comparison articles, plus
live checks recorded inline (PyPI wheel listings, `uv audit --help`, a real deptry run, `gh api` on
this repo). Every adopted candidate has since been run against this repo end to end — each §'s
Verification entry records the result, and the two that were only ever a report (deptry, lychee)
stay in §15.

## Design

### 1. `deps.py` — `audit`

`uv audit` (uv 0.10.12+, OSV-backed) wrapped as a task. Verified live: uv 0.11.19 on this machine
has it, with `--locked`, `--no-dev`, `--only-group`, and `--output-format json`.

```
inv deps.audit    # uv audit --locked
```

[DECISION: `--locked`, not a re-resolve. It audits exactly what `uv.lock` commits to, which is what
a consumer actually installs, and it keeps `deps.py`'s single-writer discipline intact — `lock` is
the only task in this package that may rewrite the lock file. A re-resolving audit would report on a
dependency set nobody has.]

[DECISION: no suppression mechanism. A vulnerable transitive dependency with no fixed version stops
the task loudly, matching `contributing/task-module-conventions.md`'s "stop loudly and say what to
run next". An ignore list would be a second place where "which advisories do we accept" lives, with
no expiry. Build one only when a real unfixable advisory blocks work.]

[DECISION: standalone, not in `check`. The result changes when the OSV database changes, not when
the code does, so a gate step would fail a commit that changed nothing — and would make `precommit`
require network in every consumer. This is the rule-1 case that motivated the rule.]

### 2. `quality.py` — `check` gains `deps.check`

`inv deps.check` (`uv lock --check`) exists today and is in no gate. CI only covers it by accident:
`bootstrap.sh` runs `uv sync --locked`, which fails on drift. So a `pyproject.toml` edit without a
re-lock passes `precommit` locally and fails in CI — the divergence `~/AGENTS.md`'s "the gate is
what CI runs" rule exists to prevent. It is offline, deterministic, needs no `.venv`, and qualifies.

### 3. `quality.py` — `workflow_check` gains zizmor

actionlint covers workflow correctness; nothing covers workflow security, and `publish.yml` carries
`id-token: write` for PyPI Trusted Publishing. zizmor is offline static analysis (its online audits
are opt-in behind a token), ships on PyPI, and is complementary to actionlint rather than
overlapping — so it qualifies for the gate.

[DECISION: folded into the existing `workflow_check` task rather than given its own. Precedent is
`format_check`, which runs ruff and dprint under one name. One task per question the developer asks
("are my workflows OK?"), not one per binary. Both tools file-gate on the same
`.github/workflows/*.yml` list, so the no-op-cleanly contract is unchanged.]

### 4. `quality.py` — `dockerfile_check` (hadolint)

New gate step, file-gated on tracked `Dockerfile`/`*.Dockerfile` paths, `require_tool("hadolint")`
inside the branch exactly as `shell_check` does.

[DECISION: hadolint and `docker build --check` are not substitutes and both are adopted, at
different tiers. Measured: Docker's built-in checks are **21 rules**, almost entirely build
semantics and casing (`StageNameCasing`, `FromAsCasing`, `LegacyKeyValueFormat`, `UndefinedVar`,
`CopyIgnoredFile`, `SecretsUsedInArgOrEnv`, …). hadolint is ~100 `DL####` rules **plus embedded
ShellCheck over every `RUN` body** — apt pinning, `apt-get update` layer merging,
`--no-install-recommends`, `ADD` vs `COPY`, `latest` base tags, root user. For this repo's two
Dockerfiles — `debian:bookworm-slim` + apt + a non-root user — hadolint's slice is the one with
findings in it. Docker's slice is real but needs a daemon, so it lands in the integration tier
(§10).]

[PITFALL: an earlier pass in this sweep recorded that the PyPI wrapper downloads the hadolint binary
at install time, which would have made `uv sync` depend on GitHub releases for every consumer. That
is wrong — PyPI's file list for `hadolint-py` 2.15.1.2 shows real platform-tagged wheels
(manylinux_2_17_x86_64 12.2 MB, macosx universal2 21.4 MB, win_amd64 15.6 MB) with the binary
inside, the same shape as `shellcheck-py`. The 8 KB sdist is the download-at-install fallback for
platforms with no wheel. Check the actual file list, not a search summary, before rejecting a
wrapper on packaging grounds.]

The accepted cost is ~12 MB in every consumer's venv, including consumers with no Dockerfile — the
same dependency-weight concern as
[`2026-08-24-devpi-dependency-weight.md`](2026-08-24-devpi-dependency-weight.md).

No `.hadolint.yaml` until a suppression is actually needed, matching the `.shellcheckrc` posture: an
exclusion lands in a file with an inline reason, following kubernetes' precedent, rather than as a
flag on the call.

### 5. `docs.py` — `link_check`, hand-rolled

Extract markdown links, resolve the relative ones against the containing file, assert each target
exists. Offline, deterministic, zero dependency, so it qualifies for the gate. Wired into
`quality.check`'s `pre=[...]` by importing it there — the same cross-module pattern `check` already
uses for `testing.unit`.

Scope: relative file links only. Not external URLs, not anchors/fragments, not HTML.

[DECISION: hand-rolled rather than lychee, against the usual "prefer the maintained external
project" default, on two measured facts. `lychee-bin` — the only maintained PyPI wrapper — is a
**78.1 MB** manylinux x86_64 wheel, 6.5× hadolint's, shipped to every consumer for link checking.
And it has exactly **one release ever** (0.24.2, uploaded 2026-05-01 15:58, seventeen minutes after
upstream's own `lychee-v0.24.2` at 15:41): current with upstream today, but a single data point is
not the version-tracking record `~/AGENTS.md` asks for. The lighter prior art is dead —
`pytest-check-links` last released 2024-04, `linkcheckmd` 2021-02. The need is narrow enough
(relative links inside one repo) that ~40 lines covers it.]

Why this earns a gate slot at all: [`plan-docs`](../CONTRIBUTING.md)'s retirement procedure says the
finishing grep must return no live pointers, and nothing enforces it. This plan's own first revision
shipped two dangling citations to a plan retired mid-session — the exact failure, on the first try.

### 6. `testing.py` — `untested_modules`, `coverage`

Two tasks, answering two different questions:

- `untested_modules` — every module under `src/<pkg>/` has a `tests/unit/test_<module>.py`.
  Deterministic, offline, no-ops cleanly where either directory is absent, so it goes in `check`'s
  `pre=[...]` alongside `unit`.
- `coverage` — `pytest --cov`, report only, standalone. No `--cov-fail-under`.

[DECISION: the file-existence check is the gate half and coverage is the report half, not the other
way round. The unit tier is `MockContext` command-string assertion, so a line-coverage number
largely measures how much mocking was written — `test-tiers.md` already records two real `dist.py`
bugs that survived full unit coverage. A threshold on that number is metric-gaming waiting to
happen. "Which module has no tests at all" is the question that has a true answer, and
`test-tiers.md` already states the convention it enforces.]

### 7. `quality.py` — `verify_types`, and `tests/unit/test_types.py`

`py.typed` plus `invoke-stubs` make this package's types a public contract that nothing currently
tests. Both halves adopted:

- `inv quality.verify-types` — `basedpyright --verifytypes repo_tasks`, a completeness report over
  the public surface. Standalone, not in the gate: its output is a report, and a consumer package's
  own completeness is not this gate's business.
- `tests/unit/test_types.py` — `assert_type` assertions pinning what a consumer actually sees: that
  `@task` preserves the decorated function's signature, and that `from invoke import task` resolves
  as a public re-export. These are exactly the two gaps `invoke-stubs` exists to close
  (`contributing/type-checking.md`), and a stub regression would currently surface only as noise in
  every consumer.

### 8. `ci.py` — new module, `status`

`inv ci.status` — recent GitHub Actions runs for a branch and whether any failed, wrapping
`gh run list`. Exists because push-triggered CI on a repo with direct-to-main pushes fails silently:
nobody watches the Actions tab, and §11's `deps.audit` job makes that worse by adding a failure mode
nobody's commit caused.

Needs `gh`, an authenticated account, and network → `require_tool("gh")`, never in the gate, and it
carries the §12 requirement marker.

[DECISION: a standalone task, not wired into `gitflow`'s push paths. gitflow's `--push` steps cover
the release flow, which is not where these pushes happen — direct pushes to `main` are, per
`~/AGENTS.md`'s personal-repo rule. A preflight in gitflow would guard the path that needs it
least.]

### 9. Shipped config: `pytest.ini` and `ruff.toml`

Both files exist twice — the root copy governs this repo, `src/repo_tasks/configs/*` is the shipped
canonical copy. Changes land in the root copy, then `configs.promote --apply`.

`pytest.ini`:

```ini
addopts = -ra --strict-markers --strict-config
xfail_strict = true
filterwarnings =
    error
```

[DECISION: ignores, when needed, go in the shared shipped file rather than triggering the unbuilt
`configs.local.toml` mechanism. The dependency set behind these warnings is family-uniform (invoke,
uv, pytest, bump-my-version), so a warning that needs silencing almost certainly needs it
everywhere. `configs.local.toml` stays a spec until something genuinely repo-specific appears.]

[PITFALL: the coupling this buys is real and worth stating up front — an upstream deprecation lands
and every repo in the family goes red at once, unblocked only by an ignore landing here, a version
bump, and `configs.pull` in each consumer. It is a reasonable bet only because the baseline is
currently zero: the 294-test run prints no warnings section at all.]

`ruff.toml` — `select` gains `PT` (flake8-pytest-style), `FURB` (refurb), `PGH` (blanket-suppression
hygiene). Select-then-triage as with `PL`/`TRY`: turn on, run, ignore individual codes with a stated
reason rather than pre-guessing.

[DECISION: `PT` is the one that matters most for this repo's shape — 294 tests, fixture-dense. Its
contested rules (ruff #8796) get ignored individually after seeing real hits. `ERA` was considered
and dropped: this family's prose-comment density makes commented-out-code detection a false-positive
generator. The `S`/bandit subset (`S602`/`S603`/`S607`) was offered and not taken.]

### 10. `docker.py` — `check`, and its integration test

`docker build --check` against each discovered image. Needs a daemon, so it is a standalone task and
belongs to the integration tier; the tier already builds both images for real, so the marginal cost
is one invocation. `tests/integration/` asserts it exits 0 for this repo's own Dockerfiles.

### 11. `.github/workflows/`

`ci.yml`:

- `permissions: contents: read` — currently inherits the repo default.
- `concurrency` with `cancel-in-progress` — superseded runs currently keep burning.
- `timeout-minutes` on each job.
- A second job running `inv test.unit` across a **3.11 / 3.12 / 3.13 / 3.14 matrix**. The
  `quality.check` job stays single-version — the matrix exists to make `requires-python = ">=3.11"`
  a true claim, and the unit tier is 0.5 s with no Docker, so four of them cost nothing.
- An `inv deps.audit` step gated to `github.event_name == 'push'` (main only), not on pull requests.

[DECISION: audit on push to main, no cron schedule yet — the user's call, explicitly not starting a
cadence. The gap this leaves is the one a schedule would close: an advisory landing during a quiet
week is invisible until the next push. `ci.status` (§8) is the mitigation, and a schedule stays
available later.]

[PITFALL: `enable-cache` on `astral-sh/setup-uv` was listed here as a gap and is not one. Its
default is `auto`, which already enables the cache on GitHub-hosted runners for exactly the `push`
and `pull_request` events this workflow uses — it is disabled only for release/tag,
`pull_request_target`, and `workflow_run` events, and on self-hosted runners. Setting it explicitly
would be noise. Read the action's own input defaults before recording a missing-option finding.]

[DEFERRED: the `deps.audit` CI step itself, blocked on
[`2026-08-24-devpi-dependency-weight.md`](2026-08-24-devpi-dependency-weight.md). `uv audit` is red
today over two `setuptools` 81.0.0 advisories fixed in 83.0.0, and the lock cannot move:
`devpi-server` requires `setuptools<=81` and `pyramid` requires `<82`. Adding the step now means
knowingly red CI. Deferred rather than worked around — narrowing the step's scope, or building the
suppression list §1 deliberately did not build, would each bake a devpi workaround into shipped
code. Everything else in this section landed.]

`publish.yml` — SHA-pin `actions/checkout` and `astral-sh/setup-uv` to full-length commit SHAs with
the version tag in a trailing comment.

[DECISION: pin `publish.yml` only, not every workflow, and no dependabot. That file is the one
holding `id-token: write` against PyPI Trusted Publishing, so it is where a compromised action would
actually cost something. Pinning everywhere without dependabot means pins rot; adding dependabot
means a recurring PR stream on repos whose owner pushes straight to `main` and reviews no PRs. One
file's pins are maintainable by hand.]

### 12. Non-gate tasks declare what they pull

Every task outside `check`'s pre-chain opens its docstring with what it needs, in a fixed greppable
form, and a unit test asserts that every such task has one. The convention is documented in
[`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md).

Partially a formalization: `test.integration`, `test.workflows`, and `test.smoke` already say "Needs
a reachable Docker daemon" in prose. What is missing is uniformity and enforcement — the new tasks
in this plan (`deps.audit`: network; `ci.status`: network + `gh` auth; `docker.check`: daemon;
`quality.verify-types`: none) triple the count.

[DECISION: a docstring convention with an enforcing test, not a `requires()` runtime preflight. The
runtime half already exists where it can work — `require_tool` handles "binary missing" with the
command that fixes it. "Is the network reachable" is a probe that is itself a network call, and "is
Docker up" duplicates what the failing command reports anyway. The gap is that the requirement is
invisible before running, which is a documentation problem with a test behind it.]

### 13. `tests/unit/conftest.py` — socket guard

An autouse fixture disabling sockets for the unit tier (`--disable-socket --allow-unix-socket`),
alongside the existing `tmp_cwd`/`isolated_home`. `test-tiers.md` promises the tier needs "no
Docker, no network, nothing outside tmp_path"; two of the three are enforced structurally and
network is enforced by nothing.

[DECISION: `pytest-socket` goes in this repo's own `dev` group, **not** in the exported
`repo-tasks-quality` manifest. The fixture lives in test structure, which this package does not ship
(`test-tiers.md`: config and the quality manifest, never tests — that is `scaffoldapy`'s half), so
shipping the plugin to consumers who have no fixture using it would be pure weight.]

[DECISION: verified compatible with the `db-defaults` skill's picks before adopting, since that
skill's whole point is real local backing services rather than mocks. Every default there is
in-process or file-backed — stdlib `sqlite3`, `sqlalchemy`+`alembic`, `duckdb`, `tinydb`,
`diskcache`, SQLite `FTS5`, `huey`, `apscheduler`, `blinker`, `ladybug`, `pathlib` — and none opens
a socket, so the guard cannot reach them. `qdrant-client` is the one that can go either way, and it
splits exactly along the intended line: embedded mode (`path=`/`:memory:`) passes, while
`QdrantClient(url=…)` is blocked. That is the guard enforcing the stated goal — contained local
services pass, coupling to a separately deployed service fails loudly in the unit tier.]

[DEFERRED: seeding the same autouse fixture into `scaffoldapy`'s generated repos, which is where
consumers would get it. Now
[`2026-08-27-generated-test-layout.md`](2026-08-27-generated-test-layout.md), which widened it: the
split and the guard are generated together, and a flat `tests/` gets neither. This item assumed the
seeding is what would move `pytest-socket` into `repo-tasks-quality`; the manifest move happened
first and on its own merits (see `contributing/test-tiers.md`), so only the generated tree is left.]

### 14. Considered and rejected

Recorded so a later sweep does not re-litigate them:

- **`pre-commit`** — rejected in the retired scaffolding plan's §C3 (a second runner, config format,
  and mental model beside invoke, which already aggregates tools behind one command).
  `~/AGENTS.md`'s rule against mechanisms that fire behind an agent's back reinforces it. Unchanged.
- **gitleaks / secret scanning** — unnecessary. `gh api repos/TheodoreAD/repo-tasks` reports
  `secret_scanning: enabled` and `secret_scanning_push_protection: enabled` already, and Trusted
  Publishing means no PyPI token exists to leak. Push protection is the layer that matters; a
  gate-side scanner would be redundant weight in every consumer.
- **`yamllint` / `taplo lint`** — YAML's two real surfaces here are workflows (actionlint, zizmor)
  and Helm charts (`helm lint`), both already covered by purpose-built tools. A general linter would
  add noise, not coverage.
- **License compliance** — permissive throughout, personal repos. Revisit if a consumer goes
  corporate.
- **`configs.diff` as a gate step** — read-only, so it dodges the silent-mutation objection that
  keeps `configs.pull` standalone, but this repo's root config files are _deliberately_ allowed to
  lead the packaged copies (that is what `configs.promote` is for). A gate step would fire on the
  state the design calls normal.

### 15. Deferred

- [DEFERRED: **deptry**. Run ad hoc during this sweep and it earned its keep immediately — see the
  finding below — but adopting it means a permanent dependency plus per-repo false-positive config
  that the shipped-config model has nowhere to put. Re-run it by hand when dependencies change.]

  What it found, recorded so the next run is not a surprise: `bump-my-version` and `repo_tasks` (×2,
  the dogfooding self-import) are false positives — shelled out and self-referential respectively.
  `python-dotenv` is reported unused and genuinely is (`rg dotenv` over `src/`, `tests/`, `tasks.py`
  returns nothing), but it stays: it is a deliberate forward-looking dependency for local
  `.env`-based configuration of task options, a well-worn pattern. Not a defect, and not to be
  "cleaned up" by a future pass. Also worth knowing: deptry does not check dev groups for unused
  entries at all, so it would never have caught a stale `repo-tasks-quality` entry — the thing that
  motivated looking at it.

- [DEFERRED: **a scheduled `deps.audit` cadence**. Push-to-main only for now, by explicit decision.
  The uncovered case is an advisory landing during a week with no pushes.]

- [DEFERRED: **SHA-pinning every workflow, plus dependabot** to keep the pins fresh. Only
  `publish.yml` is pinned now; see §11's decision for why the pair was not taken on.]

- [DEFERRED: **external link and anchor checking**. §5's task covers relative file links only.
  `lychee-bin` remains the tool if this is ever wanted, at 78 MB and with its maintenance record
  worth re-checking first.]

- [DEFERRED: **ruff `S602`/`S603`/`S607`** — the non-noise slice of bandit, relevant because
  shelling out is what this package does. Offered during the sweep and not taken; the whole `S`
  family stays correctly rejected.]

## Files touched

| file                                      | change                                                                                                                                              |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/repo_tasks/deps.py`                  | `audit` task (§1)                                                                                                                                   |
| `src/repo_tasks/quality.py`               | `check` pre gains `deps.check`, `untested_modules`, `link_check`; `workflow_check` gains zizmor; new `dockerfile_check`, `verify_types` (§2–§4, §7) |
| `src/repo_tasks/docs.py`                  | `link_check` task + relative-link helper (§5)                                                                                                       |
| `src/repo_tasks/testing.py`               | `untested_modules`, `coverage` (§6)                                                                                                                 |
| `src/repo_tasks/docker.py`                | `check` task — `docker build --check` (§10)                                                                                                         |
| `src/repo_tasks/ci.py`                    | new module — `status` (§8)                                                                                                                          |
| `src/repo_tasks/__init__.py`              | wire the `ci` collection                                                                                                                            |
| `pytest.ini` + `src/repo_tasks/configs/`  | `filterwarnings`, `xfail_strict` (§9)                                                                                                               |
| `ruff.toml` + `src/repo_tasks/configs/`   | `PT`, `FURB`, `PGH` (§9)                                                                                                                            |
| `zizmor.yml` + `src/repo_tasks/configs/`  | new shipped config — the `unpinned-uses` policy (§3)                                                                                                |
| `src/repo_tasks/configs.py`               | `zizmor.yml` in `_CONFIG_FILES`; zizmor/hadolint in the tool→distribution map                                                                       |
| `pyproject.toml`                          | `repo-tasks-quality` gains zizmor, `hadolint-py`, `pytest-cov`; `dev` gains `pytest-socket`                                                         |
| `tests/unit/conftest.py`                  | autouse socket guard (§13)                                                                                                                          |
| `tests/unit/test_types.py`                | new — `assert_type` contract (§7)                                                                                                                   |
| `tests/unit/test_*.py`                    | one per new task, `MockContext` command-string assertions                                                                                           |
| `tests/unit/test_requirements.py`         | §12's derived enforcement, keyed on (module, name) rather than name                                                                                 |
| `tests/integration/`                      | `docker build --check` against this repo's Dockerfiles (§10)                                                                                        |
| `tests/*/Dockerfile`                      | DL4006 pipefail, numeric `USER`, two inline declines (§4)                                                                                           |
| `.github/workflows/*.yml`                 | permissions, concurrency, timeouts, 3.11–3.14 unit matrix, SHA pins (§11); the §3 security fixes                                                    |
| `contributing/task-module-conventions.md` | the §12 requirement-marker convention                                                                                                               |
| `contributing/test-tiers.md`              | the socket guard as the third structural enforcement (§13)                                                                                          |

Consumers do not change until `configs.pull` + `ensure_deps` run there — see
[`contributing/consumer-sweep.md`](../contributing/consumer-sweep.md). The `repo-tasks-quality`
manifest changes (zizmor, hadolint-py, pytest-cov) **and** a new shipped config file appears
(`zizmor.yml`), so this is a sweep-triggering release on both halves at once — `configs.diff` in
each consumer will report drift in the config list and in the dev group.

## Verification

Per §. What each one asked for, and what it actually produced:

1. **`deps.audit`** — runs against this repo's real lock and exits 0; unit test pins the command
   string. Confirm exit code directly, never through a pipe.
2. **`deps.check` in the gate** — delete a dependency from `pyproject.toml` without re-locking and
   confirm `inv quality.check` fails where it currently passes.
3. **zizmor** — run against all three workflow files; every finding triaged before the step is
   allowed into the gate. Confirm the no-op-cleanly path on a repo with no workflows.

   Done. Four classes of finding, all fixed on their merits rather than suppressed: `artipacked`
   (every checkout left the job token in `.git/config`), `template-injection`
   (`${{ inputs.project }}` pasted into a `run:` block in a job holding `packages: write`),
   `excessive-permissions` (`id-token: write` at workflow level in `publish.yml`), `cache-poisoning`
   (`setup-uv`'s `auto` cache is off for a tag push but on for the `workflow_dispatch` path the same
   file carries). `unpinned-uses` is the one policy override — see the shipped `zizmor.yml`. Proved
   it gates by dropping one `persist-credentials: false`: actionlint stays clean, the task exits 13.

4. **hadolint** — run against both Dockerfiles; expect findings on `clean-os.Dockerfile`'s apt
   usage. Triage each before gating. Confirm the file-gated no-op on a Dockerfile-free repo.

   Done, four findings. `--no-install-recommends` and the apt-lists cleanup were already there, so
   the real ones were DL4006 (a piped `curl | sh` with no pipefail — a failed download exits 0 and
   commits a layer with no uv in it) and DL3066 on the sample image (`USER app` fails an
   orchestrator's runAsNonRoot check, which reads the uid without the image's `/etc/passwd`). Both
   fixed. DL3008 and DL3066-on-the-fixture declined inline. Proved it gates: `debian:bookworm-slim`
   → `debian:latest` exits 1 on DL3007.

5. **`link_check`** — must flag a deliberately broken relative link, and must return clean on
   `contributing/` + `plans/` as they stand after this plan's own citations are fixed.
6. **`untested_modules`** — must name a module whose test file is temporarily renamed. `coverage`
   just has to produce a number. It does: 98% over 1324 statements.
7. **`verify_types` / `test_types.py`** — the `assert_type` module must fail if `invoke-stubs` is
   removed from the environment. That is the regression it exists for; prove it by removing it once.
8. **`ci.status`** — run against this repo's real Actions history.
9. **pytest.ini** — `filterwarnings = error` with the suite green proves the zero-warning baseline
   held; `xfail_strict` needs a temporary xpass to prove.
10. **`docker.check`** — exits 0 for both Dockerfiles via the integration tier. Done, and the tier
    also carries the failing case (`FromAsCasing`, a rule hadolint does not have) so the passing one
    is not vacuous.
11. **CI** — the matrix job must actually run four interpreters (read the job list, not the summary
    line); `inv test.workflows` (act) before pushing a workflow change.
12. **§12's test** — must fail when a new non-gate task is added without a marker. It did better
    than that: adding `docker.check` exposed a bug in its own derivation, since it keyed gate steps
    by bare function name and `check` names three different things here.
13. **Socket guard** — a temporary unit test making an HTTP call must fail; the full existing suite
    must stay green, which is what proves the guard doesn't reach the file-backed fixtures. Both
    confirmed; `SocketBlockedError` is raised independently of `filterwarnings = error`.

The whole-plan gate: `inv quality.precommit` green, and the consumer sweep run against
`power-user-linux-setup` and `scaffoldapy` — naming which gate ran in each, per
`contributing/type-checking.md`'s "rolling this out to a consumer".

## The consumer sweep, 2026-08-27

Both consumers swept against `f01d135`. What ran, and what it found:

**`power-user-linux-setup`** (`d18b38d`..`bbb0df5`) — `inv quality.precommit` green, 376 unit tests.
12 zizmor findings across three workflows and 16 ruff `PT`/`FURB` hits, all fixed. Two `artipacked`
findings declined inline: `devcontainer.yml`'s `publish-stable` and `docs` jobs push with the
credentials the checkout leaves behind, so "fixing" them would break the job being flagged. Its
`docker/Dockerfile` was already hadolint-clean. Its `uv.lock` pins `repo-tasks`, so the pull needed
`uv lock --upgrade-package repo-tasks` first — see consumer-sweep.md's second pitfall.

**`scaffoldapy`** (`fc9fff3`..`79cb374`) — both gates, which is the only claim worth making here:
`inv quality.precommit` green (27 tests) **and** `inv test.integration` green, all ten rendered
combinations passing the generated repo's own gate.

That e2e tier is what justified its own existence. It found four things nothing else would have:

1. **A defect in this package.** `untested-modules` demanded a `test_init.py` for a docstring-only
   `__init__.py`, which every generated repo has — all ten combinations failed on it. Fixed in
   `f01d135`, which meant a second push and a second `inv repo-tasks.update` mid-sweep.
2. **A template gap.** `models.py` and `parse.py` shipped with no seed test, so five combinations
   failed the same check for a real reason.
3. **§9's coupling, twice, and not from any new tool.** The shipped `pytest.ini`'s
   `filterwarnings = error` turned copier's `DirtyLocalWarning` into 21 failures in `scaffoldapy`
   itself, and starlette's `TestClient` deprecation into a collection error in every generated web
   service. §9's decision — "ignores go in the shared shipped file" — assumed a family-uniform
   dependency set, and a consumer's own dependencies are exactly where that stops holding. Both
   fixed locally instead: a scoped `catch_warnings` around `copier.run_copy`, and `httpx2` (which
   starlette prefers when present) in the web-service template's dev group.
4. **That the template's `ci.yml` needed the same zizmor fixes as `scaffoldapy`'s own** — the two
   files are byte-identical by design, and only the generated half is what new projects inherit.

[DECISION: `httpx2` over suppressing the starlette warning. It is upstream's own instruction rather
than a workaround, `web_service` with `fetch_strategy = none` pulls in no other HTTP client so it
adds exactly one package, and it was verified in a scratch venv — FastAPI's `TestClient` with
`httpx2` installed passes under `-W error`. Suppression would have left every generated web service
on a deprecated path with a filter hiding the notice.]

---
status: planned
updated: 2026-08-20
---

## Context

`dev_env.py` currently owns one venv-lifecycle task (`venv`: plain `uv sync` + `direnv allow`) as
part of its dev-loop bootstrap ceremony (`setup` = `venv` + `claude_hook`). That single task
conflates three concerns that need to vary independently: (1) core venv lifecycle (create/delete/
resync from `uv.lock`), (2) dev-loop-only glue (direnv auto-activation, Claude Code's Bash-tool
hook), (3) dependency-lock-file operations (lock/list/tree), which `dev_env.py` doesn't touch at
all today. `uv sync`'s own default behavior is also a latent trap for this repo's stated design
goals: with no `--locked`/`--frozen` flag it will silently *update* `uv.lock` to match
`pyproject.toml` whenever they've drifted — exactly the "mutate state for convenience instead of
surfacing an issue" failure mode this repo's other tasks are built to avoid (`quality.check` is a
no-mutation CI-style gate; `gitflow.py` never silently auto-resolves a merge conflict, it fails
loudly and prints what to do next). There is also currently no supported way to install this
project's tasks non-editable, e.g. for a docker image or CI job — every `uv sync` call installs the
project (and any workspace members) in editable mode, uv's own default.

Two new task modules plus a `dev_env.py` trim close this gap: `venv.py` (pure lifecycle,
lock-respecting, CI-aware) and `deps.py` (lock-file operations — the only module allowed to write
`uv.lock`). `dist.py` (build/publish/query a wheel) is the sibling third module of this same
request, designed separately in `plans/2026-08-19-python-package-tasks.md` (updated 2026-08-20 to
match this split, renamed from that plan's original `python_pkg.py`) — not repeated here.

Single-implicit-project only for now (Phase 1, no `[tool.uv.workspace]` in the consumer's root
`pyproject.toml`), same phasing as `plans/2026-08-19-monorepo-workspace-foundation.md`: every task
below runs bare `uv sync`/`uv lock`/`uv tree`, no `--project`/`--package` flag. Phase 2 iterates
`projects.discover_python_projects(c)` the same way `dist.py`'s Phase 2 will.

Every `uv` flag named below was confirmed against this repo's installed `uv 0.11.19`
(`uv sync --help`, `uv lock --help`, `uv tree --help`, `uv pip list --help`), not assumed from
memory.

## Design

### 1. `src/repo_tasks/venv.py` (new) — pure venv lifecycle, never writes `uv.lock`

- `sync(c, no_editable=False, no_dev=False)` — the one core primitive: `uv sync --locked` (+
  `--no-editable` / `--no-dev` per flag). `--locked` "assert[s] that the uv.lock will remain
  unchanged" — fails loudly if `uv.lock` is missing or stale relative to `pyproject.toml`, instead
  of uv's own default of silently regenerating it. The failure message this task prints points at
  `inv deps.lock` as the deliberate fix — `venv.py` itself never runs `uv lock`, ever.
  `--no-editable` installs the project and any workspace members as real, non-editable packages —
  the CI/docker mode the request asked for: a docker image or CI artifact build shouldn't link back
  to a live source tree the way a dev-loop editable install does. `--no-dev` skips the dev
  dependency group, for a slim runtime-only install (a production image doesn't need `ruff`/
  `pytest`). Both flags default off — an ordinary local dev sync stays a plain `uv sync --locked`.
- `create(c)` — `pre=[sync]`, no args: the friendly first-time-after-clone entrypoint (matches the
  literal "create" ask), reusing `sync`'s defaults rather than a second implementation — `uv sync`
  itself doesn't distinguish "first create" from "later resync," so neither should this module.
- `delete(c)` — `shutil.rmtree(".venv")` if present, else a no-op message. Exact `docs.clean`
  pattern (`_SITE_DIR`-style path constant, exists-check, `shutil.rmtree`), same shape, different
  directory.
- None of these three touch direnv or the Claude Code hook — that stays dev-loop-specific glue,
  owned by `dev_env.py` (§3 below), so `venv.py` is equally usable from a Dockerfile or CI job with
  no direnv/Claude Code assumptions baked in at all.

### 2. `src/repo_tasks/deps.py` (new) — the only module allowed to write `uv.lock`

- `lock(c, upgrade=False, package=None)` — `uv lock`, `--upgrade` for a full re-resolve, or
  `--upgrade-package <package>` for one deliberate bump (matches the exact command README.md
  already documents for a consumer bumping pinned `repo-tasks` itself: "a later fix reaches a
  consumer only via a deliberate `uv lock --upgrade-package repo-tasks`"). This is the *only* task
  in the whole package that ever runs `uv lock` — `venv.sync`'s `--locked` flag guarantees a stale
  lock fails instead of getting silently rewritten by any other task.
- `check(c)` — `uv lock --check` ("Check if the lockfile is up-to-date"), read-only, no venv
  needed. A fast standalone gate — e.g. a cheap first CI step that fails before spending time on a
  full `venv.sync`, or a local sanity check right after hand-editing `pyproject.toml`.
- `list(c, outdated=False)` — `uv pip list` (flat table of what's actually installed in `.venv`
  right now); `outdated=True` adds `--outdated` to show what's installed vs. what the index
  actually has newest.
- `tree(c, outdated=False)` — `uv tree` (full resolved dependency tree from `uv.lock`);
  `outdated=True` adds `--outdated` ("Show the latest available version of each package in the
  tree") — the "what could I upgrade to" view `list` alone can't give, since `list` only sees
  what's installed, not the tree's why-is-this-here structure.
- Every task here is read-only except `lock` itself — `list`/`tree`/`check` never write anything,
  safe to run anywhere, anytime, including CI, with no side effects.

### 3. `dev_env.py` trim — dev-loop glue only, delegates lifecycle to `venv.py`

- `venv` task's body becomes `venv.create(c)` (imported) + the existing `direnv allow` /
  "direnv not found" logic, unchanged behavior for a consumer — `inv dev-env.venv` and
  `inv dev-env.setup` keep working exactly as README.md already documents, just delegating the
  actual sync to the new module instead of inlining `uv sync` directly. No consumer-facing rename;
  purely an internal delegation, so this stays additive rather than breaking.
- `claude_hook` and `setup` unchanged.

### 4. CI/docker usage (the "we need a CI/docker mode" ask)

No separate `ci=True` task flag — deliberately named after what each flag actually does
(`no_editable`, `no_dev`) rather than one opaque `ci` boolean, since a real CI *test* job usually
still wants dev deps (`pytest`, `ruff`) installed to run `quality.check`, while a docker *runtime*
image wants neither dev deps nor an editable install. A Dockerfile or CI job calls
`inv venv.sync --no-editable` (test job: still wants dev deps) or
`inv venv.sync --no-editable --no-dev` (runtime image: neither) directly — `venv.create`'s
defaults stay dev-loop-only (editable, direnv-wired), so there's no risk of a docker build
accidentally picking up direnv-allow side effects it has no use for.

### 5. Lock-file discipline (the "never update the lock file" ask)

Enforced structurally, not by convention: `venv.sync`/`venv.create` always pass `--locked`, never
`--frozen` (which would skip the staleness check entirely rather than surface it) and never a bare
`uv sync` (which would silently rewrite the lock on drift). `deps.lock` is the sole writer, in the
whole package, of `uv.lock`. This holds identically in local dev and CI — "doubly so in CI" from
the request is satisfied by there being no special-cased CI leniency anywhere: the exact same
`--locked` assertion runs everywhere, and CI simply has no interactive human to shrug the failure
off, so it just fails the job instead of silently resolving anything.

## Files touched

- `src/repo_tasks/venv.py` (new)
- `src/repo_tasks/deps.py` (new)
- `src/repo_tasks/dev_env.py` — `venv` task delegates to the new module; `claude_hook`/`setup`
  unchanged
- `src/repo_tasks/__init__.py` — nest `venv`/`deps` collections into `ns` alongside the existing
  ones
- `README.md` — document `venv.*`/`deps.*` alongside the existing `dev_env`/`quality` mentions, and
  the CI/docker no-editable usage pattern from §4
- `tests/test_venv.py`, `tests/test_deps.py` (new, `MockContext`/`Result` style matching
  `tests/test_quality.py`/`tests/test_dev_env.py`); `tests/test_dev_env.py` updated for the
  delegation change in §3

## Verification

- Unit tests mocking `c.run` for every `venv.py`/`deps.py` task's exact command-string construction
  (`--locked`, `--no-editable`, `--no-dev`, `--upgrade`, `--upgrade-package`, `--outdated`), same
  pattern as `tests/test_quality.py`.
- `inv venv.create` exercised against this repo itself, confirming `.venv` ends up synced and
  `direnv allow` still runs.
- `inv venv.sync --no-editable` exercised locally, confirming (e.g. via `uv pip show repo-tasks`)
  the project installs non-editable rather than as a live source link.
- A deliberately staled `uv.lock` (hand-edit `pyproject.toml` without re-locking) confirms
  `venv.sync` fails loudly rather than mutating the lock, and that `deps.lock` (and only
  `deps.lock`) resolves it.
- `inv deps.check` exercised against both a fresh and a deliberately-staled lock, confirming the
  read-only pass/fail without ever touching `.venv`.

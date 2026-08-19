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
(`uv sync --help`, `uv lock --help`, `uv tree --help`, `uv pip list --help`, `uv export --help`),
not assumed from memory. The Docker/CI layer-caching design (§1's `no_install_project`, §6) was
additionally checked against real-world usage, not invented in isolation: Astral's own
[`uv-docker-example`](https://github.com/astral-sh/uv-docker-example) (`multistage.Dockerfile`) and
[Docker integration guide](https://docs.astral.sh/uv/guides/integration/docker/) both use the
identical bind-mount-lockfile-then-`--no-install-project` two-phase pattern this plan adopts, and
the same split shows up independently in community devcontainer/CI setups — it's the standard
idiom, not a bespoke one.

2026-08-20 review: confirmed the deps-only-venv ask (build `.venv` with just third-party packages,
no repo code) is exactly this standard pattern, not a novel need — added §1's `no_install_project`
flag and §6's Docker recipe below. Also surfaced a real cross-cutting gotcha while researching:
[astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643) — `uv sync --locked
--no-install-project` (and `--locked` generally) fails if *only* the project's own version changed
in `pyproject.toml`, because `uv.lock` embeds that version too. This directly affects
`release-management.md`'s `version.bump`: a bump commit needs `deps.lock` re-run *before* it's
committed, or the very next `--locked` sync (correctly) fails until someone notices and relocks.
Not this plan's bug to fix — `version.py` is `release-management.md`'s file — but worth flagging
there as a known interaction (see that plan for the actual fix).

## Design

### 1. `src/repo_tasks/venv.py` (new) — pure venv lifecycle, never writes `uv.lock`

- `sync(c, no_editable=False, no_dev=False, no_install_project=False)` — the one core primitive:
  `uv sync --locked` (+ `--no-editable` / `--no-dev` / `--no-install-project` per flag). `--locked`
  "assert[s] that the uv.lock will remain unchanged" — fails loudly if `uv.lock` is missing or
  stale relative to `pyproject.toml`, instead of uv's own default of silently regenerating it. The
  failure message this task prints points at `inv deps.lock` as the deliberate fix — `venv.py`
  itself never runs `uv lock`, ever. `--no-editable` installs the project and any workspace members
  as real, non-editable packages — the CI/docker mode the request asked for: a docker image or CI
  artifact build shouldn't link back to a live source tree the way a dev-loop editable install
  does. `--no-dev` skips the dev dependency group, for a slim runtime-only install (a production
  image doesn't need `ruff`/`pytest`). `--no-install-project` ("Do not install the current
  project") syncs *only* third-party dependencies, skipping the local project entirely — the
  deps-only venv the request asked for, so a CI job or Docker builder stage can build/cache that
  layer from just `pyproject.toml`+`uv.lock`, before the repo's own code is even present, and reuse
  it across builds no matter whether `--no-dev` is also set. §6 below spells out the concrete
  Docker recipe. All three flags default off — an ordinary local dev sync stays a plain
  `uv sync --locked`.
- `create(c)` — `pre=[sync]`, no args: the friendly first-time-after-clone entrypoint (matches the
  literal "create" ask), reusing `sync`'s defaults rather than a second implementation — `uv sync`
  itself doesn't distinguish "first create" from "later resync," so neither should this module.
- `delete(c)` — `shutil.rmtree(".venv")` if present, else a no-op message. Exact `docs.clean`
  pattern (`_SITE_DIR`-style path constant, exists-check, `shutil.rmtree`), same shape, different
  directory.
- `install_wheel(c, wheel="dist/*.whl")` — `uv pip install --no-deps <wheel>`. The prod-with-wheel
  path's final piece (§6): once a builder stage has already synced third-party deps via
  `sync(no_install_project=True, ...)`, this adds *only* the already-built project package
  (`dist.build`'s output, `plans/2026-08-19-python-package-tasks.md`) on top of that same venv —
  `--no-deps` means it never re-resolves or touches anything `sync` already installed, so it can't
  silently pull a dependency version that diverges from what's locked/cached. Distinct from `sync`
  deliberately: it takes a wheel path, not the project source tree, and has no `--locked` concept
  of its own (there's no resolution happening to assert against).
- None of these touch direnv or the Claude Code hook — that stays dev-loop-specific glue, owned by
  `dev_env.py` (§3 below), so `venv.py` is equally usable from a Dockerfile or CI job with no
  direnv/Claude Code assumptions baked in at all.

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
- `export(c, output="requirements.txt", no_dev=False)` — `uv export --format requirements.txt
  --locked --no-editable [--no-dev] -o <output>` (confirmed flags via `uv export --help`; `--locked`
  keeps the same never-silently-mutate posture as everything else here). Not needed by the Docker
  recipe in §6 below (that path copies the already-synced `.venv` directly, no requirements file
  involved) — this exists for every *other* consumer of a plain pinned dependency list: SBOM/
  vulnerability scanners (`pip-audit`, Trivy, Snyk), or any non-uv-aware CI step that only speaks
  `requirements.txt`.
- Every task here is read-only except `lock` itself — `list`/`tree`/`check`/`export` never write
  anything, safe to run anywhere, anytime, including CI, with no side effects.

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

### 6. Docker multi-stage recipe: dev (editable + mounted source) vs. prod (wheel in a venv)

Adapts Astral's own `multistage.Dockerfile` two-phase layer split (Context above) to end with a wheel
install (`dist.build` → `venv.install_wheel`) instead of a second `uv sync` of the full project —
per review, preferred over the equally-valid sync-only variant Astral's example uses, because it
gives "build once, ship the identical artifact everywhere": the same wheel this stage installs can
also go straight to `dist.publish`, so the container is provably running what got published, not a
second from-source build that merely resolves to the same versions.

- **Deps-only layer** (builder stage, shared by dev, CI test jobs, and the prod build — this is
  the request's "venv without the repo code"): bind-mount just `uv.lock` + `pyproject.toml`
  (nothing else copied in yet, so Docker's layer cache — and a CI cache keyed the same way — stays
  valid across every commit that doesn't touch either file), then
  `inv venv.sync --no-install-project` (add `--no-dev` for a prod build). Produces a `.venv` with
  every third-party dependency installed and nothing of the project itself.
- **Dev image**: stops here, plus the source tree bind-mounted (not copied) into the running
  container and `PATH` pointed at `.venv/bin` — editable-equivalent in effect, since the mounted
  source is live; no `sync`/`install_wheel` step needed beyond the deps-only layer above once
  mounted, matching Astral's documented dev workflow (mount project, exclude `.venv` from the
  mount).
- **Prod image**: `COPY` the real source in (this stage only, never the final one),
  `inv dist.build` (produces `dist/*.whl`), then `inv venv.install_wheel` against the *same*
  `.venv` populated by the deps-only layer — adds only the project package, no re-resolution.
  Final stage: fresh minimal base, non-root user (`groupadd`/`useradd --system`, matching
  `uv-docker-example`'s pattern exactly), `COPY --from=builder --chown=<user> /app/.venv
  /app/.venv` only — no source tree, no `uv` binary, no build tooling in the shipped image.
- This recipe is documented here (the module design) but the actual Dockerfile content lives in a
  consumer repo — `plans/2026-08-19-dogfood-sample-service.md` is where this repo's own example
  Dockerfile will exercise it for real, and `plans/2026-08-19-docker-image-tasks.md`'s `docker.py`
  is what builds/pushes whatever Dockerfile a consumer writes using this pattern. Neither of those
  plans currently spells out multi-stage internals; worth a follow-up note in
  `dogfood-sample-service.md` once its Dockerfile is actually written, rather than duplicating this
  recipe a third time.

## Files touched

- `src/repo_tasks/venv.py` (new)
- `src/repo_tasks/deps.py` (new)
- `src/repo_tasks/dev_env.py` — `venv` task delegates to the new module; `claude_hook`/`setup`
  unchanged
- `src/repo_tasks/__init__.py` — nest `venv`/`deps` collections into `ns` alongside the existing
  ones
- `README.md` — document `venv.*`/`deps.*` alongside the existing `dev_env`/`quality` mentions, the
  CI/docker no-editable usage pattern from §4, and the deps-only/wheel-install Docker recipe (§6)
- `tests/test_venv.py`, `tests/test_deps.py` (new, `MockContext`/`Result` style matching
  `tests/test_quality.py`/`tests/test_dev_env.py`); `tests/test_dev_env.py` updated for the
  delegation change in §3
- `plans/2026-08-19-release-management.md` — a short "known interaction" note pointing at
  astral-sh/uv#15643 (Context above): `version.bump` needs `deps.lock` re-run before its commit,
  or the next `--locked` sync fails until relocked

## Verification

- Unit tests mocking `c.run` for every `venv.py`/`deps.py` task's exact command-string construction
  (`--locked`, `--no-editable`, `--no-dev`, `--no-install-project`, `--upgrade`,
  `--upgrade-package`, `--outdated`, `export`'s flags), same pattern as `tests/test_quality.py`.
- `inv venv.create` exercised against this repo itself, confirming `.venv` ends up synced and
  `direnv allow` still runs.
- `inv venv.sync --no-editable` exercised locally, confirming (e.g. via `uv pip show repo-tasks`)
  the project installs non-editable rather than as a live source link.
- `inv venv.sync --no-install-project` exercised locally against a clean `.venv`, confirming
  third-party deps land but `repo-tasks` itself does not (`uv pip show repo-tasks` reports "not
  found"); then `inv dist.build` + `inv venv.install_wheel` exercised on top of that same venv,
  confirming the project appears afterward without uv re-touching any dependency already installed
  (diffed `uv pip list` before/after `install_wheel`).
- A deliberately staled `uv.lock` (hand-edit `pyproject.toml` without re-locking) confirms
  `venv.sync` fails loudly rather than mutating the lock, and that `deps.lock` (and only
  `deps.lock`) resolves it. Separately, a version-only edit (bump `pyproject.toml`'s `version`
  with no dependency change, no relock) reproduces astral-sh/uv#15643 against this repo's own lock,
  confirming the known-interaction note above is accurate before it ships as guidance.
- `inv deps.check` exercised against both a fresh and a deliberately-staled lock, confirming the
  read-only pass/fail without ever touching `.venv`.
- `inv deps.export` exercised locally, confirming the generated `requirements.txt` matches
  `uv.lock`'s pinned versions and omits the local project itself.

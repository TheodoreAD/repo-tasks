---
status: in-progress
updated: 2026-08-23
---

## Context

`repo-tasks`' own tasks mutate a real `$HOME`, not just the consumer repo they're invoked from:
`selfinstall.py` (`uv tool install` — the global daily-driver install), `agents.py` (wires Claude
Code's Bash-tool hook into `~/.claude/settings.json`, writes `~/.cache/claude-code/*`), `direnv.py`
(`direnv allow`), and `configs.py`/`configure.py`'s config-distribution machinery. None of this is
exercised by the existing test suite: unit tests mock `c.run` (never touching a real filesystem),
and `tests/integration/` (`plans/2026-08-22-local-index-and-registry-testing.md`) only covers
`dist.py`/`docker.py` against real network services (a local `devpi-server`, `registry:3`) — nothing
there stands up an isolated `$HOME` to test the user-wide-effects tasks against.

Testing these against the actual dev machine's real `$HOME` is both risky (a bug could clobber a
real `~/.claude/settings.json` or shell rc file) and not reproducible in CI, where there is no
pre-existing `$HOME` state to begin with. Needs a genuinely clean OS + `$HOME` — and specifically
**non-root**, since every one of these tasks is meant to stay user-scoped and never require root;
running the container as root would silently let a task get away with writing somewhere a real
non-root user never could, defeating the point of the test.

## Design

### 1. `tests/integration/clean-os.Dockerfile`

Deliberately minimal: `debian:bookworm-slim` + `ca-certificates`/`curl`/`git`/`direnv`, one non-root
`tester` user (`useradd --create-home`), `uv` installed via the official install script under that
user's own `~/.local/bin`. No Python pinned beyond what `uv` itself bootstraps on demand — matches
this repo's own dev-loop (`uv` manages its own Python versions), and keeps the image generic enough
to reuse for any future user-wide-effects test, not just one specific task.

Deliberately **not** at the repo root. `projects.discover_docker_images(c)`
(`plans/2026-08-19-monorepo-workspace-foundation.md` Design §2) treats a root-level `Dockerfile` as
this repo's own implicit shippable `[[docker]]` image — this Dockerfile is test infra only, and has
nothing to do with `plans/2026-08-19-dogfood-sample-service.md`'s eventual real sample-service
image. Living under `tests/integration/` keeps it out of that discovery path entirely and colocates
it with the only thing that uses it.

### 2. `clean_os_container` fixture (`tests/integration/conftest.py`)

Mirrors the existing `docker_registry` fixture's `testcontainers` pattern (module-scoped, a `with`
block managing teardown), extended with an image build/publish step the existing fixtures don't
need:

- **The image is built and pushed via `repo_tasks.docker`'s own real `build`/`push`/`release` tasks
  — not hand-rolled build code.** Dogfooding these tasks against a real Dockerfile is the actual
  point of this whole exercise (`docker.py`/`docker-registry-integration.md` were until now only
  ever exercised against a synthetic `FROM scratch` image in `test_docker_integration.py`, or mocked
  `c.run` in unit tests). Same monkeypatched-`discover_docker_images` pattern that test already
  uses, pointed at `clean-os.Dockerfile` and this module's `docker_registry` fixture instead of a
  throwaway scratch image: `docker_tasks.release.body(ctx)` runs the full `build` → tag `:latest` →
  push `:test` → push `:latest` sequence for real, against a real (if local) registry. A fresh
  `Context`/`pytest.MonkeyPatch()` stand in for the `c`/`monkeypatch` fixtures, which are
  function-scoped and can't be depended on by this module-scoped fixture.
- [PITFALL: docker-py's `images.build()` eagerly resolves credentials for **every** registry listed
  in `~/.docker/config.json` before building anything, so a single stale entry fails a build that
  never touches that registry. Found live 2026-08-23, while this fixture still used testcontainers'
  `DockerImage` directly: a stale `gcr.io` → `docker-credential-gcloud` entry (tied to a deleted GCP
  account, since fixed on this machine) failed the whole build. `docker.py`'s tasks always shell out
  to the plain `docker` CLI (`c.run(...)`), never the Python SDK, so they are immune — which makes
  this a corollary of dogfooding them, not a workaround adopted to avoid the SDK.]
- `DockerContainer(f"{image.image}:latest").with_command("sleep infinity")` keeps the container
  alive for `exec()` calls afterward — no long-running server process to wait on, unlike
  `devpi_index`/`docker_registry`.
- The repo source is bind-mounted read-only at a scratch path, then `cp -r`'d (via `.exec()`) into
  `/home/tester/repo-tasks` inside the container — a real, writable, isolated copy, so a test
  running e.g. `uv sync` or `git` operations against it can't mutate the host checkout and doesn't
  fight the read-only mount.

### 3. Scope for this plan: the fixture itself, not yet the real mutating tests

This plan lands the Dockerfile + fixture + one smoke test proving the fixture works (non-root, clean
`$HOME`, repo source present and readable) — not a real `selfinstall.py`/`agents.py`/ `direnv.py`
test yet. Those are real, separate pieces of follow-up work once this infra exists; scoping them in
now would be speculative given no such test has been written or reviewed yet.

[DEFERRED: the real mutating tests — `selfinstall.py`, `agents.py`, `direnv.py` exercised against
this isolated `$HOME` — are the actual point of building the fixture, and none exist yet. This is
the next piece of work on this plan, not a separate concern someone else picks up.]

[DEFERRED: fixture scope needs revisiting when that first mutating test is written. The smoke test's
module scope is fine only because it is the only test in its module; once several tests share one
container's `$HOME`, they can leak state into each other — which `devpi_index`/`docker_registry`
avoid only because every test there uploads or pushes a distinctly-named artifact, a property a
`$HOME`-mutating test does not have. Decide module-shared vs. a fresh container per test then, with
a real test in hand, rather than guessing now.]

## Files touched

- `tests/integration/clean-os.Dockerfile` (new)
- `tests/integration/conftest.py` — add `clean_os_container` fixture
- `tests/integration/test_clean_os_integration.py` (new) — smoke test only, per Design §3

## Verification

- **Confirmed (2026-08-23):** `docker_tasks.release.body(ctx)` builds `clean-os.Dockerfile`, tags
  `:latest`, and pushes both `:test`/`:latest` to the local `docker_registry` fixture for real —
  `repo-tasks`' own `docker.build`/`push`/`release` tasks, dogfooded end to end, not a synthetic
  scratch image.
- `clean_os_container` starts from that pushed image; `id -u` inside it is non-zero (non-root).
- `$HOME` starts clean — no `.claude`, no repo-tasks-specific state, before anything runs.
- The bind-mounted repo source lands at `/home/tester/repo-tasks` and is readable (`pyproject.toml`
  present).
- Real `selfinstall.py`/`agents.py`/`direnv.py` tests against this fixture are not written yet —
  tracked by the `[DEFERRED:]` items in Design §3, which is what keeps this plan `in-progress`.

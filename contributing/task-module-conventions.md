# Task module conventions

The rules every task module in `src/repo_tasks/` follows, and why. `AGENTS.md` states the ones an
agent needs up front; this file is the reasoning, including what was rejected.

These emerged across `quality.py`, `venv.py`, `deps.py`, `dist.py`, `docker.py`, `version.py`, and
`gitflow.py` rather than being designed once — but they are consistent, and a new module is expected
to follow them.

## Never silently mutate state for convenience

The single most load-bearing rule. A task surfaces a problem; it does not paper over one.

Concretely, `venv.sync`/`venv.create` always pass `--locked` to `uv sync` — never `--frozen` (which
skips the staleness check rather than surfacing it) and never a bare `uv sync` (which silently
rewrites `uv.lock` on drift). The failure message points at `inv deps.lock` as the deliberate fix.

This holds identically in local dev and CI. There is no special-cased CI leniency anywhere: the same
assertion runs everywhere, and CI simply has no human to shrug it off.

`gitflow.py` follows the same posture from the other direction — it never auto-resolves a merge
conflict, and there is no `warn=True` in the file. `*_finalize`'s `git merge --ff-only` fails loudly
rather than overwriting unexpectedly diverged history.

## Single-writer rules

Exactly one module may write each piece of shared state:

| state                     | sole writer  |
| ------------------------- | ------------ |
| `uv.lock`                 | `deps.lock`  |
| a project's version field | `version.py` |

Every other `venv.*`/`deps.*` task is read-only with respect to the lockfile; `dist.py` reads the
version and never writes it. The point is that two modules racing to touch one value is a bug class
that simply cannot occur if only one of them can write.

A corollary worth stating because it is easy to violate accidentally: a module that needs locking
done should call `deps.lock`, not shell out to `uv lock` itself. See
`plans/2026-08-23-uv-lock-on-version-bump.md`, where this constraint shapes the fix.

## No-op cleanly when an artifact kind is absent

A task must be safe to run in a repo that has none of what it operates on. `quality.shell_check`
established the pattern for "no `*.sh` files here"; `helm.py` follows it for zero `[[helm]]` entries
(each task prints a short "nothing to do" note and returns). `docker.py` currently diverges: its
tasks raise when zero images are discovered — tolerable while nothing wires them into a composite;
tracked in `plans/2026-08-19-helm-chart-tasks.md`. An explicit `--project` naming something
undiscovered is an error in every module, per "ambiguity is an error" below — the no-op rule is
about the artifact kind being absent entirely, not about a named target missing.

This is what makes it safe to wire a task unconditionally into a future top-level composite without
a per-repo opt-out.

## Smart defaults, so zero config is a real option

The common case is a single-project repo with no `repo-tasks.toml` at all, and it must keep working
with no configuration — the README's "that's the entire file — no local override" ergonomics must
not regress.

- No `[tool.uv.workspace]` → the repo root's own `[project]` table **is** the one implicit project.
- No `repo-tasks.toml` / no `[[docker]]` entries → a `Dockerfile` at the repo root is treated as one
  implicit image, named after the repo's python project (so `group` matches naturally) or the
  directory name if there is no `pyproject.toml`.

Discovery lives in `projects.py`. Every task module calls it rather than hardcoding "the repo root."

Ambiguity is an error, not a guess: `--project` naming something undiscovered raises rather than
silently picking one.

## Name flags after what they do, not after who runs them

`venv.sync` takes `no_editable`, `no_dev`, and `no_install_project` — deliberately not one opaque
`ci=True` boolean. A CI _test_ job usually still wants dev deps installed to run `quality.check`,
while a docker _runtime_ image wants neither dev deps nor an editable install. One boolean cannot
express that, and would have to guess.

## Opt into expensive paths, don't default into them

When a capability carries real cost and nothing currently needs it, accept it as a flag from day one
but leave the common path cheap — rather than either building around it unconditionally or dropping
it and reworking later.

`docker.build`'s `--platforms` is the worked example. Multi-arch builds are single-arch by default;
passing `--platforms=linux/amd64,linux/arm64` opts into `docker buildx`. Building around buildx
unconditionally would have imposed three costs with no cross-arch deployment target to justify them:
a `buildx create --use` builder bootstrap, QEMU cross-compilation that can run 5–20x slower for
compute-heavy build steps unless native-arch runners are used, and a `--push`-only constraint —
buildx cannot `--load` a multi-platform result into local `docker images` the way single-platform
builds can.

That last one leaks into the task's own contract, which is why `build`'s docstring has to say that
multi-platform builds push as part of `build` itself. A flag that changes what a task _does_, not
just how, needs saying so where the caller will see it.

## Stop loudly, and say what to run next

Any command that stops short of "the whole flow is done" — a PR was opened and needs a human, a
guard clause tripped — prints exactly what to run next, via `gitflow.py`'s private
`_next_steps(*lines)` helper. Established there, but meant to apply to any task anywhere in this
package with the same "stops for an external reason" shape.

The alternative is leaving the caller to read source to find out what happens now, which is what
this avoids.

## Release-time actions stay out of the quality composite

`fix`/`check`/`precommit` are every-commit actions. Building and publishing are not, so `dist.*`,
`docker.*`, and `version.*` are never folded into them.

`dist.publish` in particular is never invoked from any automated composite, given its irreversible
external-facing nature — always a deliberate, standalone `inv dist.publish`. See
[`versioning.md`](versioning.md) for the release path and
`plans/2026-08-22-pypi-publish-integration.md` for the irreversibility that motivates it.

## Freshness via `pre=`, not by trusting what's on disk

`dist.build` has `pre=[clean]` so a stale wheel from a previous version can never survive into a
fresh build; `dist.publish` has `pre=[build]` so publish always ships a just-built `dist/` rather
than whatever happened to be sitting there. Same shape as `docs.build`'s own `pre=[clean]`.

This is the build-freshness counterpart to the lock-freshness discipline above — same principle,
different state.

## One module per facility

Named after what it owns (`venv.py`, `deps.py`, `direnv.py`, `agents.py`), never a broad grab-bag.

This was corrected once, in practice: `dev_env.py` originally held venv lifecycle, direnv wiring,
and the Claude Code hook together, and ended up contending with `venv`/`deps`/`dist` for the same
kind of responsibility. It was split — `direnv.py` took `allow`, `agents.py` took `claude_hook` and
its settings.json helpers — leaving `dev_env.py` with no logic of its own, purely composing siblings
via `pre=[...]`.

A module that only composes other modules' tasks into a one-command entrypoint is fine and owns
nothing. Avoid naming a module after a composite's _purpose_ in a way that reads like it could own
real responsibilities belonging to `venv`/`deps`/`dist`.

## Import siblings as `from .sibling import name`

Not `from . import sibling`, and not `import repo_tasks.sibling as sibling`. Every module here is
also wired into `__init__.py`, so those two forms make the submodule depend on `__init__.py`, which
already depends on it — a `reportImportCycles` false positive in basedpyright. Targeting the
submodule file directly avoids it. See `version.py`/`gitflow.py` for the pattern.

## Echo every command that does something

`c.run(..., echo=True)` for any command with an effect — what ran should be visible and
copy-pasteable, not inferred from output.

The exceptions are internal queries whose _output_ is the point rather than the command: reading the
current branch, listing open release branches, resolving the origin URL, finding `*.sh` files, and
querying remote tags. Those use `hide=True` (plus `warn=True` where a non-zero exit is a normal
answer) and are not echoed, because echoing plumbing the caller didn't ask for is noise. The rule is
about actions, not about every subprocess.

## Configuration lives in its own file

Each tool gets its own dedicated config file rather than being consolidated into `pyproject.toml` —
`ruff.toml`, `pyrightconfig.json`, `dprint.json`, `pytest.ini`, `repo-tasks.toml`. Python-project
data (`[tool.uv.workspace]`, each member's `[project].version`) is the exception, because it
unavoidably has to live in `pyproject.toml`.

Docker images and Helm charts aren't modeled by `uv` workspaces at all, which is why they get
`repo-tasks.toml` rather than being bolted onto `pyproject.toml`.

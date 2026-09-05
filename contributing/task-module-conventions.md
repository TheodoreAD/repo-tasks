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
| `uv.lock`'s resolution    | `deps.lock`  |
| a project's version field | `version.py` |

Every other `venv.*`/`deps.*` task is read-only with respect to the lockfile; `dist.py` reads the
version and never writes it. The point is that two modules racing to touch one value is a bug class
that simply cannot occur if only one of them can write.

The two rows meet in one place: `uv.lock` embeds the project's own version, and that field belongs
to the second row, not the first. `version.bump` rewrites it there — a text substitution inside
bump-my-version's own commit, anchored on the `name = ...` line above it — and never runs `uv lock`;
`deps.lock` still owns every resolved dependency in the file. See
[`versioning.md`](versioning.md#uvlock-moves-with-the-bump) for why that split, and not a re-lock
after the bump, is the fix.

A corollary worth stating because it is easy to violate accidentally: a module that needs locking
done should call `deps.lock`, not shell out to `uv lock` itself.

## No-op cleanly when an artifact kind is absent

A task must be safe to run in a repo that has none of what it operates on. `quality.shell_check`
established the pattern for "no `*.sh` files here"; `helm.py`, `docker.py` and `dist.py` follow it
for zero `[[helm]]` entries / zero images / no python project (each task prints a short "nothing to
do" note and returns — a composite like `docker.release` or `dist.publish` as one unit, before its
first step). An explicit `--project` naming something undiscovered is an error in every module, per
"ambiguity is an error" below — the no-op rule is about the artifact kind being absent entirely, not
about a named target missing.

This is what makes it safe to wire a task unconditionally into a future top-level composite without
a per-repo opt-out.

The one deliberate exception is `version.py`: `bump` and `current_version` raise a clear
`ValueError` in a repo with no python project, because nothing else can supply a version — a bump
has nothing to write, and a `docker.build` asking for its default tag has nothing to be told. An
error that names the cause is the honest answer there; a silent no-op would be a bump that didn't
bump.

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

A `--project` flag must actually select. `dist.py`'s took the flag while documenting it as "Phase 1:
ignored" — harmless while a root project was the only thing that could exist, a silent
wrong-artifact bug the moment workspace members resolved. If a selection axis isn't implemented yet,
leave the flag off rather than accepting and discarding it.

[PITFALL: invoke's `pre=[other_task]` passes the caller's arguments to nothing — the pre-task runs
with its own defaults. A task that both takes `--project` and depends on another `--project`-aware
task must call it from its own body (`dist.publish` does), or it will act on the default target
while appearing to honour the flag.]

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

## A decision lives in one docstring; the others point at it

When two tasks are shaped by the same decision, write it out where it is _made_ and reference it
from the other. A second copy reads as authoritative for exactly as long as it takes the first to
change, and nothing in the gate compares two prose paragraphs.

Measured 2026-09-06. `docs.build`'s docstring opened with "In `quality.check`, because …" — a
placement `7a41c1e` had reversed, moving the build to `precommit` because `check` must not mutate —
and it also cited a `link_check` limitation that `link_check` had itself removed. `quality.check`,
`quality.precommit` and `docs.link_check` all read correctly at the time; the one paragraph holding
a **second copy of the argument** was the one that drifted, and it drifted in both of its claims at
once. It was found from a consumer's pinned checkout weeks later, because nothing in the gate reads
English.

The general form is worth stating because prose goes stale against anything it names and no linter
notices: a sibling task's placement here, a dependency's behaviour elsewhere. Reference beats
restatement wherever the two are available.

## Stop loudly, and say what to run next

Any command that stops short of "the whole flow is done" — a PR was opened and needs a human, a
guard clause tripped — prints exactly what to run next, via `gitflow.py`'s private
`_next_steps(*lines)` helper. Established there, but meant to apply to any task anywhere in this
package with the same "stops for an external reason" shape: `deps.lock` imports it for the
moved-workspace-member failure that a plain re-run never fixes, the same way `gitflow.py` imports
`version.py`'s private `_bump`.

The alternative is leaving the caller to read source to find out what happens now, which is what
this avoids.

## Release-time actions stay out of the quality composite

`fix`/`check`/`precommit` are every-commit actions. Building and publishing are not, so `dist.*`,
`docker.*`, and `version.*` are never folded into them.

`dist.publish` in particular is never invoked from any automated composite, given its irreversible
external-facing nature — always a deliberate, standalone `inv dist.publish`. See
[`versioning.md`](versioning.md) for the release path and
`plans/2026-08-22-pypi-publish-integration.md` for the irreversibility that motivates it.

## Declare what a task needs beyond a checkout

Two rules, and the second exists to keep the first honest:

1. **`quality.check`'s chain stays deterministic and offline.** A step whose answer can change
   without the code changing — an advisory database, an external URL — or that pulls a Docker image
   or a binary at run time, does not belong in the gate. That is what makes `inv quality.precommit`
   runnable in any consumer, on a plane, without a daemon. `deps.audit` is the worked example: it
   wraps `uv audit`, and it is a standalone task precisely because OSV moves on its own.
2. **A task outside the gate declares what it needs**, with `@requires(...)` from
   [`requirements.py`](../src/repo_tasks/requirements.py), above `@task`:

```python
@requires(NETWORK)
@task
def audit(c: Context): ...
```

The vocabulary is `NETWORK`, `DOCKER`, `GH`, and `requires()` rejects anything else rather than
recording a typo. It returns the task untouched, so nothing about invoke's dispatch or the stubs'
typing changes.

`tests/unit/test_requirements.py` enforces it by _derivation_ rather than from a list someone
maintains: it parses each module, collects the command strings each task builds, and maps their
leading words onto requirements. A new task that runs `docker build` without declaring `DOCKER`
fails there. It cannot see a command assembled in a module-level helper, or a library that reaches
the network without a subprocess (`dist.list-versions` via urllib, the integration tiers via
testcontainers) — those declare by hand, and the check only ever asserts that what it derives is
covered, never that a declaration is superfluous.

[PITFALL: the obvious mechanism, invoke's own `@task(klass=..., requires=...)`, costs the typing.
invoke rejects unknown kwargs (`TypeError`), so custom metadata needs a `Task` subclass — and while
`invoke-stubs` types `klass` itself, an _extra_ keyword matches none of its overloads, so `@task`
silently degrades to an untyped decorator. Measured: the decorated function's `.body` becomes `Any`
and `reportUntypedFunctionDecorator` fires, which `failOnWarnings` turns into a failed gate — the
exact regression `invoke-stubs` was written to fix. A separate decorator, generic over
`Callable[P, R]`, keeps the metadata and the types both.]

## Freshness via `pre=`, not by trusting what's on disk

`dist.build` has `pre=[clean]` so a stale wheel from a previous version can never survive into a
fresh build; `dist.publish` calls `clean` and `build` from its own body so publish always ships a
just-built `dist/` rather than whatever happened to be sitting there — from the body, not `pre=`,
because of the `--project` pitfall above. Same shape as `docs.build`'s own `pre=[clean]`.

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

## A shared suffix marks a family of interchangeable modules

`gitflow.py` and `trunkflow.py` implement the two git branching models this package supports. The
`-flow` suffix is what says they are the same kind of thing, and it is load-bearing rather than
incidental: a third model joins as `githubflow` or `gitlabflow` and needs no other change.

[DECISION: the suffix, not a shared parent namespace. `sdlc.gitflow.*`/`sdlc.trunkflow.*` was
considered and rejected — SDLC spans requirements through maintenance, and **ten of this package's
sixteen namespaces are already SDLC phases** sitting as siblings (`quality`, `test`, `dist`,
`docker`, `helm`, `docs`, `ci`, `deps`, `venv`, `configs`), so the root would promise a scope that
is visibly elsewhere. `workflow` collides outright with the GitHub Actions workflows three tasks
here are about. And a root answers a discovery question asked once — "are these alternatives?" —
while lengthening every command forever, since nobody ever types the model their repo does not use.]

The general rule: **when two modules are alternatives rather than collaborators, say so in their
names.** A parent namespace is the wrong tool, because interchangeable things are never used
together — the reader needs to recognise the class once, not navigate into it every time.

[PITFALL: do not pick such a name for where it sorts in `inv --list`. `git-trunk` and `githubflow`
both land immediately beside `gitflow` and `trunkflow` does not, which is the only argument either
had — and `githubflow` names a _different_ model (GitHub Flow branches and merges through a PR),
while `git-trunk` is an invented compound. The listing is scanned, not bisected.]

## Import siblings as `from .sibling import name`

Not `from . import sibling`, and not `import repo_tasks.sibling as sibling`. Every module here is
also wired into `__init__.py`, so those two forms make the submodule depend on `__init__.py`, which
already depends on it — a `reportImportCycles` false positive in basedpyright. Targeting the
submodule file directly avoids it. See `version.py`/`gitflow.py` for the pattern.

**A module that imports a sibling's task must declare an explicit `ns`.** `Collection.from_module`
adds every `Task` object it finds in a module's namespace, and an imported one is indistinguishable
from a defined one — so a task pulled in for a `pre=` chain gets published a second time under the
importing module's name. `quality.py` importing `testing.unit` produced `inv quality.unit` beside
`inv test.unit`; `dev_env.py` importing its three prerequisites produced `dev-env.create`,
`dev-env.allow` and `dev-env.claude-hook` beside the `venv`/`direnv`/`agents` tasks that own them.
Nothing declared any of the four and no test compared `inv --list` against what the modules define,
so they went unnoticed long enough for a consumer repo to document one of them as if it were the
real name. Both modules now end with `ns = Collection(<the tasks they actually own>)`, which
`from_module` prefers over its auto-scan; do the same in any module whose imports include a task.

## Echo every command that does something

`c.run(..., echo=True)` for any command with an effect — what ran should be visible and
copy-pasteable, not inferred from output.

That flag is load-bearing beyond the echo itself: under `REPO_TASKS_RUN_REPORT` it is what selects
the commands that get a one-line report instead, with their output folded on success and replayed on
failure (see [`quality-gate.md`](quality-gate.md#what-the-gate-prints)). So "echo anything with an
effect" is the same rule it always was, and a new task needs to know nothing else to be reported
correctly — while the internal queries below, which pass `hide=True`, stay silent in both modes.

The exceptions are internal queries whose _output_ is the point rather than the command: reading the
current branch, listing open release branches, resolving the origin URL, finding `*.sh` and workflow
files, and querying remote tags. Those use `hide=True` (plus `warn=True` where a non-zero exit is a
normal answer) and are not echoed, because echoing plumbing the caller didn't ask for is noise. The
rule is about actions, not about every subprocess.

## A task may not run anything that waits for typed input through `c.run`

A command that prompts — `docker login`, `helm registry login`, anything reading `/dev/tty` — goes
through `interactive.run_interactive`, a plain subprocess inheriting the real terminal. Never
`c.run(...)`, and **never `c.run(..., pty=True)`**, which is the shape that looks right.

[PITFALL: `pty=True` hides one bug and not the other. Without a pty, invoke echoes stdin itself and
races the child for every keystroke, so the password is printed and the child re-prompts; a pty
fixes that. On Python 3.14 invoke's stdin thread dies on the first keystroke — a 2-byte buffer
handed to `fcntl.ioctl(FIONREAD)` for a 4-byte result, which 3.14 hardened into `SystemError` — so
nothing reaches the child, pty or not, and the prompt hangs forever with no output. Upstream
pyinvoke/invoke#1070, unreleased as of invoke 3.0.3. Both were reproduced in a container across
3.10–3.14 (the `invoke-task-conventions` skill has the matrix). This package is a uv tool on the
family's default interpreter, 3.14, so the hang was the shipped behaviour of both `login` tasks from
2026-08-30 to 2026-09-05.]

[DECISION: step out of invoke's way rather than accommodate the prompt. `--password-stdin` with a
token from the environment was the other candidate and was rejected because it makes this package
handle the credential — read it, hold it, pipe it — which both `login` docstrings refuse on purpose:
the tool prompts and the tool stores, and the only thing automated is the registry host. A
subprocess with inherited stdio is exactly what typing the command at the shell does, so echo
suppression is the child's own business and nothing races it.]

[PITFALL: the unit tests asserted `c.run(..., pty=True)` verbatim and passed throughout — a mock's
call shape cannot see a runtime hang. They now assert the `run_interactive` call the same way and
have the same blind spot; the oracle for "a login actually completes" is a real terminal, which
`power-user-linux-setup`'s `tests/containers/` is the only place in the family that has.]

Audit for it with `rg 'pty=True'`; the shape is most common around credential prompts, which is
exactly where a hang is least welcome.

## Configuration lives in its own file

Each tool gets its own dedicated config file rather than being consolidated into `pyproject.toml` —
`ruff.toml`, `pyrightconfig.json`, `dprint.json`, `pytest.ini`, `repo-tasks.toml`. Python-project
data (`[tool.uv.workspace]`, each member's `[project].version`) is the exception, because it
unavoidably has to live in `pyproject.toml`.

Docker images and Helm charts aren't modeled by `uv` workspaces at all, which is why they get
`repo-tasks.toml` rather than being bolted onto `pyproject.toml`.

---
status: in-progress
updated: 2026-08-30
repo: git@github.com:TheodoreAD/repo-tasks.git
---

# A consumer's `pytest.ini` needs a line the canonical one does not have

## Context

`pytest.ini` is one of the files `configs.pull` materialises, and the file says so in its own
header: it ships to every consumer, and a change worth making is almost certainly worth making
family-wide. That works while every consumer wants the same file.

One consumer now does not. A repo whose test suite is partly async needs

```ini
anyio_mode = auto
```

in `pytest.ini` — AnyIO's plugin reads it from the ini file and there is nowhere else to put it,
because pytest reads exactly one config file and `pytest.ini` wins over `pyproject.toml` whenever it
exists. The line was added locally on 2026-08-29. `configs.pull` would silently take it back out,
and the failure that follows is loud but misleading: every async test raises rather than running,
with a warning about an un-awaited coroutine rather than a message about configuration.

So the local edit is a divergence with a countdown on it, and this is the general question rather
than that one repo's problem: **what happens when a consumer legitimately needs a line the canonical
file does not have?**

## Open questions

**Answered 2026-08-29: it is not inert, and the answer is a hard failure.** With the shipped
`pytest.ini` plus `anyio_mode = auto`, in an environment holding pytest 9.1.1 and no AnyIO:

```
ERROR: Unknown config option: anyio_mode
...
collected 1 item
============================ no tests ran in 0.00s =============================
```

Exit code 4, no test executed — because `--strict-config` is already in the file's own `addopts`,
which is what turns the unread key into a fatal error rather than a warning. The same project with
AnyIO 4.14.2 added and nothing else changed collects and passes.

**What decides which of the two a consumer gets is not whether it writes async tests.** AnyIO
registers its own pytest plugin through a `pytest11` entry point — `anyio -> anyio.pytest_plugin`,
verified in this repo's env — so the key is known wherever the package is importable, direct
dependency or not. And AnyIO arrives transitively: `bump-my-version` (a main dependency of
`repo-tasks`) pulls `httpx2`, which pulls `anyio`. So the split falls along how a consumer installs
this package, which nobody chose with pytest in mind:

| consumer                 | how it gets `repo-tasks`      | `anyio` in its lock | `anyio_mode` in a pulled `pytest.ini` |
| ------------------------ | ----------------------------- | ------------------- | ------------------------------------- |
| `power-user-linux-setup` | project dependency (git)      | yes, transitively   | accepted, silently                    |
| `scaffoldapy`            | global `uv tool`, absent here | no                  | fatal, exit 4                         |

Measured against both repos' `uv.lock` and `pyproject.toml` on 2026-08-30. That is the real hazard
in shipping the line: not that it breaks everyone, but that whether it breaks a given consumer turns
on a transitive dependency of a version-bumping tool, invisible from the config file and liable to
change the next time that graph moves.

[PITFALL: this is only measurable in a genuinely isolated environment, and the first attempt was not
one. `uv run --no-project --with pytest` from a shell with this repo's venv active reported
`plugins: anyio-4.14.2, socket-0.8.1, cov-7.1.0` and passed cleanly. `--with` layers an ephemeral
overlay over the active environment rather than replacing it — `sys.prefix` in that run was this
repo's own `.venv` — so the probe measured a machine that had AnyIO all along and produced exactly
the "it is inert" answer being tested for. Nothing here is a uv defect; the flag does what it
documents. `env -u VIRTUAL_ENV -u PYTHONPATH uv run --no-project --python 3.11 --with pytest==9.1.1`
is what actually isolates. Any future probe of the form "is this dependency absent" has the same
hole, and a plugin that auto-registers is the kind that hides in it.]

[DECISION: **No per-repo append, in any of its three shapes.** Answered 2026-08-30, and the
alternative is not "ship the line to everyone" either: `configs.pull` **derives** the line, emitting
`anyio_mode = auto` only for a consumer whose own lock contains AnyIO. That keeps the property the
append would have cost — a pulled file stays fully determined by the canonical copy plus declared
facts about the consumer, so `configs.diff` applies the same derivation and still compares exactly,
and "why does this repo's config differ" keeps one answer. The distinction the earlier framing
missed is between **derivation** (computed from something declared) and **preservation** (arbitrary
hand-edits kept across a pull); only the second has the two-answers problem. Same mechanism as route
B in `2026-08-29-python-floor-in-the-shipped-configs.md`, so the "decide these together" clause is
satisfied — one rule covers both.]

[DEFERRED: Whether `configs.diff` should report a local edit to a pulled file loudly enough to be
noticed. It compares against the canonical copy already; what is missing is anything in the routine
`quality.precommit` path that surfaces the difference, so a diverged file stays diverged silently
until someone runs the pull that reverts it. Derivation removes the immediate need — the affected
consumer stops carrying a hand-edit at all — but not the general hole, which the next hand-edit
falls into.]

## What the predicate has to be, and the one that looks right and is not

[PITFALL: **"is AnyIO installed" must not be answered in the process running the task.** The obvious
implementation — `importlib.util.find_spec("anyio")` inside `configs.pull` — reads whichever
interpreter is running `repo_tasks`, and for a consumer that gets this package as a global `uv tool`
that is the _tool's_ venv, not the consumer's. Measured 2026-08-30:

```
~/.local/share/uv/tools/repo-tasks/lib/python*/site-packages/
  anyio  anyio-4.14.2.dist-info  bump_my_version-1.5.1.dist-info  httpx2  httpx2-2.12.0.dist-info
```

`bump-my-version -> httpx2 -> anyio` puts AnyIO in the tool's own environment, so the in-process
check answers "yes" for **every** consumer — including `scaffoldapy`, whose venv has none. It would
write the line into exactly the repo the derivation exists to protect, and pytest would exit 4. The
check has to be a fact about the _target project_, and the failure mode of getting it wrong is the
original bug with a mechanism on top.]

[DECISION: **the predicate is the consumer's `uv.lock`.** Chosen 2026-08-30 over probing
`./.venv/bin/python`, which measures the exact environment pytest will use but needs a venv to
already exist — and `configs.pull` runs during bootstrap, before `venv.create`, so it would need a
fallback anyway and two paths that can silently disagree. The lock is the family's source of truth
for what `venv.sync` installs, needs no interpreter, and is independent of which `repo_tasks` is
running. It splits the two known consumers correctly, measured the same day:
`grep -c 'name = "anyio"'` gives 2 for the project-dependency consumer and 0 for the global-tool
one. The residual gap — a hand-installed AnyIO absent from the lock — is out of scope by the same
argument the family already applies elsewhere: an environment that disagrees with its lock is broken
independently of this.]

The predicate is also the right one on its own terms, not just the cheapest: the line is a no-op for
a consumer that has AnyIO transitively and writes no async tests, correct for one that writes them,
and fatal only where AnyIO is absent — which is precisely what the lock reports. And it self-heals:
if the dependency graph moves and AnyIO leaves a consumer's lock, the next pull drops the line
rather than leaving behind a key that has become fatal.

## Recommended direction

~~Measure the inert claim first~~ — done, and it went the unlucky way. ~~The general question is
live now~~ — answered 2026-08-30 by the two decisions above. What is left is implementation:

1. `configs.pull` reads the target project's `uv.lock` and emits `anyio_mode = auto` into
   `pytest.ini` only when AnyIO is in it; `_diff_config_files` applies the same derivation before
   comparing, so a correctly-derived file never reports drift.
2. The canonical `pytest.ini` carries the line with a comment saying it is derived and why — a
   reader of the shipped file should not have to find this plan to learn that the line is
   conditional, or that `--strict-config` in the same file's `addopts` is what makes an unrecognised
   key fatal rather than a warning.
3. The affected consumer's hand-edit stops being a divergence and becomes the derived output, so
   nothing there needs undoing.

Rejected: **shipping AnyIO as a `repo-tasks-quality` dependency** and then shipping the line
unconditionally. It reads well — the manifest is already where the family standardises pytest
plugins, and its own comment justifies `pytest-cov`/`pytest-socket` on the grounds that both are
inert until asked for — but the justification does not transfer. Those two are inert _as
dependencies_; AnyIO would be added for the sole purpose of making one config key parse, which makes
deliberate and permanent a coupling that is currently accidental, and puts an async framework in
every consumer's dev environment for a key most of them will never use.

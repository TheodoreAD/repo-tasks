---
status: in-progress
updated: 2026-09-12
---

# `repo-tasks.status` measures the running interpreter, not the global tool

_All three halves are now fixed: the docstring that promised otherwise, the measurement — `status`
reads uv as well and prints both numbers — and `stamp`, which keeps the active reading but says so
and warns when it is behind. The filename records the behaviour that prompted the plan, and is kept
rather than renamed because `selfinstall.py` cites it by path. What is left is two deferred items
the fixes raised rather than the defect: the third version reading, which needs the network, and
whether the tool-shadowing report `update` now prints wants a `status` or `doctor` of its own._

## Context

Found 2026-09-08 immediately after cutting `v0.3.0` and running `inv repo-tasks.update`, which is
the moment the task exists for:

```
$ inv repo-tasks.update
uv tool install --force ...repo-tasks@v0.3.0 | ok | Installed 1 executable: repo-tasks
$ inv repo-tasks.status
[repo-tasks.status] installed: 0.2.0; ...
```

`uv tool list` said `repo-tasks v0.3.0` at that moment, and the global tool's own interpreter
confirmed `0.3.0`. The update had worked; the task said it had not.

**The cause is one import.** `selfinstall.py` binds
`from importlib.metadata import version as _installed_version`, which reports the version of the
`repo_tasks` distribution **in the interpreter currently executing** — not the globally installed uv
tool. The docstring says the other thing:

> Compare the globally-installed repo-tasks version against what this repo was last `configure`d
> against

In this repo `inv` resolves through direnv to `.venv/bin/inv`, so the number it printed was this
checkout's own editable install, whose recorded metadata still said `0.2.0` because a
`bump-my-version` edit to `pyproject.toml` does not regenerate an editable install's metadata. Two
different versions, one of them reported under the other's name.

[PITFALL: **the reading is right often enough to be trusted.** In a consumer that does not install
`repo-tasks` into its own environment, `inv` _is_ the global tool, so the running interpreter and
the global install are the same thing and the docstring is true. The task is therefore correct
wherever it is usually run and wrong exactly where the question is sharpest — in a repo holding its
own copy, right after an upgrade. A `uv sync` here made both numbers `0.3.0` and the disagreement
vanished, which is worse than it sounds: the task now agrees by coincidence rather than by
construction.]

**It is not only this repo.** `power-user-linux-setup` takes `repo-tasks` as a project dependency
with a pinned `uv.lock`, so `inv repo-tasks.status` there reports the **locked** version while
claiming to report the global one — and the gap between a consumer's lock and the global tool is
precisely the drift [`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md)
records as "two different lags, both invisible from a green terminal".

## The sharper case, which is not a report

`stamp` reads the same value and **writes** it:

```python
installed = _installed_version("repo-tasks")
pinned_ref = f"@v{installed}" if f"v{installed}" in _remote_tags(c) else ""
```

It runs as part of `inv configure`, so a repo that carries its own `repo-tasks` install can stamp
`bootstrap-repo-tasks.sh` to that environment's version rather than to the one actually installed —
and because it silently falls back to an unpinned install when the tag is not real, a wrong-but-real
tag pins consumers to a genuinely older release with no warning at all. Today `v0.2.0` is a real
upstream tag, so this is live rather than hypothetical: stamping from this checkout before the
`uv sync` would have pinned `v0.2.0` on the day `v0.3.0` was released.

`version`'s docstring is the one that is already honest — "whatever `inv` process is executing this,
typically the global daily-driver install" — which suggests the distinction was understood when that
task was written and lost by the time the other two reused the helper.

## Open questions

[DECISION: **the docstring half is done, 2026-09-08 (`c55f7d4`), and it settles nothing about the
measurement.** `status` now says it reads the _active_ version and names the case where that is not
the global tool. Done separately and immediately because a docstring making a false claim is wrong
whichever way the question below goes, and this one had just misled a reader — leaving it in place
as evidence for a plan would have cost the next person the same minutes it cost the first.]

[DECISION: **`status` reads both and prints both, by default, with no flag.** The user's call
2026-09-08, on the grounds that this output is largely read by agents. A flag was considered and
rejected for the reason the run-reporting redesign already established here: the population that
would benefit is the one that never reaches for a flag, and a flag would leave the _incomplete_
answer in the default position — the same inversion that redesign existed to undo.

**The objection this plan originally recorded against reading uv was wrong and is withdrawn.** It
said the change "gives a task needing nothing today a dependency on `uv` being on PATH".
`selfinstall.py` line 23 is `_INSTALL_CMD = "uv tool install …"`; the sibling `update` task already
shells out to uv, `stamp` writes that command into the bootstrap script, and the module's docstring
opens by calling itself a manager of "this package's own daily-driver install as a global
`uv tool`". There was no new dependency class to add. Worth recording as a correction rather than
quietly fixing, because the objection was the main thing arguing for won't-fix.]

~~Does `stamp` want the same answer as `status`?~~ **No — the active reading stays, and the fix was
the one this question predicted**, settled by the user 2026-09-12 and landed the same day
(`773af0b`). The script records what this repo was last configured against, so a consumer carrying
its own pinned `repo-tasks` should stamp the version its own tooling resolves to rather than
whatever is installed globally on that machine. What changed is everything around the number: the
task prints which source it came from on every run, warns when that version is behind the newest
upstream release without overriding the pin, and separates the two causes of an empty tag list —
nothing tagged yet, and an unreachable remote — which both stamp unpinned and used to be reported as
the first.

**`stamp` was also reaching the network undeclared**, through `_remote_tags` running
`git ls-remote`, and now carries `@requires(NETWORK)`. That is the sharper finding, because nothing
was ever going to notice it: the requirements check read string literals in a task's own body only,
so a command built in a module-level helper was invisible to it — and `update`, which reaches the
same helper, was declared by hand and therefore looked like evidence the check was working.

[PITFALL: **the check's documented limit was doing the hiding.** `test_requirements.py` stated the
helper blind spot in its own docstring as a deliberate limit, with "must declare its requirements by
hand" as the mitigation — which reads as a decision rather than as a gap, and nothing measured
whether the hand-declaring was actually happening. It was, for one of the two tasks. The derivation
now follows a task into its own module's functions transitively (`3903ad5`); run against the whole
package it flagged exactly one task, which is what makes it a strengthening rather than a new
policy.]

[DEFERRED: the third reading — the latest released tag. Now that `releases/latest` resolves it is
answerable, and for an agent asking "am I current?" it is arguably the actionable number, since
neither of the two now printed says anything about what exists upstream. Kept out of the default
deliberately: it needs the network, and routine tasks in this package do not take it — the same line
that keeps `ci.check-actions` out of the gate. **This is where a flag genuinely belongs**, and it is
the one place a flag was not the wrong shape. Not built, because nobody has asked for the number.]

## Verification (2026-09-08)

`status` now prints `active: <v> (this process); global uv tool: <v> (same|differs)` and then its
existing stamp comparison, with `installed` renamed to `active` throughout so no line names a source
it does not read. `_global_version` shells out to `uv tool list` and returns `None` for both "uv
absent" and "not installed as a tool" — neither is an error, since a consumer taking this package as
a project dependency legitimately has no global install.

Four unit tests: the two readings differing, agreeing, no tool install, and uv exiting non-zero. The
last asserts the active reading still lands, since it is the half that needs no uv.

[PITFALL: **the parser was written against fabricated output and then checked against real output,
and only the second one is evidence.** `uv tool list` prints `repo-tasks v0.3.0` followed by its
executables as `- inv`, `- invoke`, `- repo-tasks` — so the tool's own name appears twice, once as a
heading and once as an indented executable, and a looser match would read the second. The live run
returns `0.3.0` correctly. The "differs" branch is covered only by unit test, because forcing a real
mismatch means downgrading the machine's global install for the sake of a check.]

## Verification (2026-09-12)

`stamp`'s three new paths are unit-tested — pinned and current, pinned but behind the latest
release, and an empty tag list — plus the existing not-a-real-tag fallback, all through
`MockContext` with no network. The strengthened requirements derivation was run against the package
before the declaration was added, and failed on `selfinstall.stamp` alone; that failure is the
oracle, since a check that passes either way proves nothing.

~~Does a composite task have to declare what its `pre` chain needs?~~ **No — it is computed, not
restated**, settled by the user 2026-09-12 and landed the same day (`71a0caf`, `b8541f9`).
`requirements.effective(task)` walks `pre` and unions what the chain declares, so `inv configure`
answers `network` and `inv testing.all` answers `docker` with nothing hand-maintained anywhere. The
alternative — each composite declaring its own union — was rejected on the objection this package
already makes to every hand-maintained list: a second copy of a derivable fact, wrong the first time
a step in the chain gains a requirement, and silent about being wrong.

The rule now has a check from the declaration side to match the one from the command-string side:
`effective(quality.check)` and `effective(quality.precommit)` must be empty, which catches a gate
step that declares a requirement by hand — a library-mediated network call, say, that has no command
to derive from.

~~The reading surface, which is what the question was actually about.~~ **Built the same day**
(`5ed82c5`): `README.md`'s "What a task needs beyond a checkout" table is generated from the
declarations by `inv docs.generate`, and `inv docs.generate-check` fails the gate when it drifts —
so `inv configure` answering `network` is readable without opening three modules, and `effective`
has a consumer that is not a test. The reasoning is in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Generation runs first".

What is left is the deferred network reading above, and the doctor question at the end of the file.
`stamp`'s source question, and both measurement questions, are answered.

## Should the stamp template pin an interpreter? (2026-09-12)

Recorded as deferred earlier the same day because nothing in **this** repo pointed at it — the work
belongs to the stamp template, the note sat in another repo's plan, and a session editing `stamp`
had no reason to open it. `power-user-linux-setup`'s
`plans/2026-08-23-invoke-repo-tasks-tool-conflict.md` carries it as an item whose own text says
"belongs to `repo-tasks`' stamp template, not here": `bootstrap-repo-tasks.sh` stamps a bare
`uv tool install` while that repo's `bootstrap.sh` passes `--python "${UV_PYTHON_DEFAULT}"`, "so the
stamped script installs against whatever interpreter uv happens to pick".

~~Does the template want `--python`?~~ **No, and the premise does not survive measurement** — that
last clause is wrong. Settled by probing uv 0.11.19 with isolated `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`,
so nothing on this machine moved:

| probe                                                | what uv reported, and chose                                      |
| ---------------------------------------------------- | ---------------------------------------------------------------- |
| the real stamped git-URL shape, `UV_PYTHON` unset    | `>=3.11` from `requires-python` metadata -> cpython 3.14.5       |
| a package declaring `>=3.9,<3.10`, `UV_PYTHON` unset | `>=3.9, <3.10` from `requires-python` metadata -> cpython 3.9.25 |
| the same package, `UV_PYTHON=3.14`                   | `3.14` from explicit request -> installed onto 3.14 regardless   |

**The bare command is already bounded below by this package's own `requires-python`**, through a git
URL included — uv fetches the target's static metadata before choosing an interpreter, then takes
the newest installed one satisfying it. It cannot land on 3.10.

**The two bootstrap scripts already agree on this machine, but not by the mechanism the item
assumed.** `UV_PYTHON=3.14` is exported into every shell by `power-user-linux-setup`'s
`[packages.uv-env]`, and `uv tool install --python` reads that env var — so both land on 3.14
because of the variable, not because uv's unconstrained default happens to match.

**And the third row is what settles it: an explicit request _overrides_ `requires-python` rather
than narrowing it.** A package declaring `>=3.9,<3.10` installed onto 3.14 with no warning anywhere
in the output. A version pinned into a template that every consumer regenerates would therefore
silently ignore both that consumer's own floor and whatever its machine or CI had chosen — the one
shape that is wrong for a shared artifact. Where a machine wants to state a choice, `UV_PYTHON` or a
**global** `.python-version` is the place; a **local** `.python-version` is deliberately ignored for
tool installs.

Landed as a comment at `_INSTALL_CMD` in `selfinstall.py` (`6d30b1c`) rather than only here, because
the question gets asked by whoever is editing that line.

## The shadowing guard, the other half of that item (2026-09-12)

Deferred an hour earlier in this same plan and then done, so the bracket is gone rather than
answered in place. `update` now reports when `invoke` is installed as a uv tool of its own beside
this one (`dbe84e4`) — the third of the three paths `power-user-linux-setup`'s plan names, after its
own `bootstrap.sh` and this repo's stamp template.

~~Report, refuse, or remove?~~ **Report.** Removing another tool mutates machine state outside this
package, which is the first rule in
[`../contributing/task-module-conventions.md`](../contributing/task-module-conventions.md) — a task
surfaces a problem rather than papering over one — and refusing to install would leave the one
command that moves the global install unable to move it. Which of the two tools should survive is
not answerable from here: something else on the machine may want bare `invoke`, so the message names
both directions and `next_steps` carries the command.

[DECISION: **the reading is generalised out of `_global_version` rather than added beside it.**
`_installed_tools` parses `uv tool list` once into name -> version, and the version lookup becomes a
`.get` on it. That is a widening, so it needed a guard the old code did not: `name == "repo-tasks"`
could not misread anything, while a dict comprehension reads `- vhs` as the tool `-` at version
`hs`. The first character now has to be alphanumeric, which is what separates a tool heading from
the executables listed under it, and a test holds it.

None and an empty dict are kept distinct — uv failing to answer is not the same as uv having nothing
installed, and the reporter stays silent on the first rather than inventing a warning from it.]

[PITFALL: **there is still no machine-readable `uv tool list`**, checked against uv 0.11.19's own
`--help` rather than assumed: `--show-paths`, `--show-version-specifiers`, `--show-with`,
`--show-extras`, `--show-python`, `--outdated`, and nothing else. The plan that raised this asked
whether reading `~/.local/share/uv/tools/` directly would be more honest; it would not — that path
is only uv's default, and `uv tool list` honours `UV_TOOL_DIR` where a hardcoded path silently would
not.]

Verified against the real listing and not only through `MockContext`, because this module has
already been caught once writing a parser against fabricated output: 16 tools parsed from this
machine's own `uv tool list`, with no executable line read as a tool — `nuitka`'s three included.
`invoke` is correctly absent, that split having been cleared by hand on 2026-08-23, so the reporter
stays silent here and the fabricated-listing test is what covers the case that fires.

[DEFERRED: whether `status` should report the same thing, or whether it wants a `repo-tasks.doctor`
of its own. `power-user-linux-setup`'s plan calls it "worth doing in the same pass" and the marginal
cost is now near zero, since `_installed_tools` is already there and `status` already calls it. Left
alone deliberately: that plan pairs the shadowing case with a second failure that shares its symptom
— invoke resolving `tasks.py` by walking up from **cwd**, so a command run against another repo
collects the calling repo's tasks — and says a check reporting only the first "would still leave the
cwd half undiagnosed, and the two are hard to tell apart from the symptom". A doctor task that
answers half the question is worth designing rather than reaching for.]

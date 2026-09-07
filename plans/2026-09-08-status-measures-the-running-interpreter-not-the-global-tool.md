---
status: idea
updated: 2026-09-08
---

# `repo-tasks.status` measures the running interpreter, not the global tool

_The docstring that promised otherwise is fixed; what remains is whether the measurement itself
should change. The filename still describes the behaviour, which is unchanged._

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

[NEEDS CLARIFICATION: should the **measurement** change? Reading the global tool properly means
asking uv (`uv tool list`, or running the installed `repo-tasks` executable and reading its own
answer) rather than asking this process — a real change, and one that gives a task needing nothing
today a dependency on `uv` being on PATH. The docstring fix has made the task honest without making
it useful: nobody is now answering the drift question `status` was named for, and the argument for
leaving it that way is that the question may belong to a different task entirely.]

[NEEDS CLARIFICATION: does `stamp` want the same answer as `status`? It might not. `stamp` records
what a consumer's bootstrap should install, and an argument exists that the active environment is
the right source for that — it is what the person running `configure` is actually using. If so the
fix there is a docstring and a printed line saying which version it pinned and where that number
came from, not a change of source.]

[NEEDS CLARIFICATION: is there a third reading nobody is computing — the latest released tag? Now
that `releases/latest` resolves (it returns `v0.3.0` as of 2026-09-08), "are you behind the latest
release" is answerable, and it is plausibly what someone running `status` wants over either of the
two versions currently in play.]

## Recommended direction

Rough, and the measurement question comes first because the other two follow from it.

The remaining step, if one is wanted, is to make `status` print **both** numbers with their sources
named — the active install and what the global tool reports — since the whole failure here was one
number appearing under the other's name. That needs no new dependency when the global reading is
unavailable, and would have made the original symptom self-explaining rather than alarming.

**It is now legitimate to close this as won't-fix**, which was not true before the docstring landed.
The task is honest today, and the drift question it does not answer has no recorded instance of
anyone needing it — this plan's own evidence is a session confused by the wording, not by the
absence of the reading.

Whatever is decided, the fix belongs with a test that runs the two readings apart. A unit test with
a mocked context cannot see this: the defect is which interpreter answers, and a mock supplies the
answer.

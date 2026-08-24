---
status: landed
updated: 2026-08-25
---

## Migrated to

Landed 2026-08-25 as option (a): `_bumpversion_config` adds a `uv.lock` file entry, anchored on the
`name = "<project>"` line, plus `pre_commit_hooks = ["uv lock --check"]`, so the lock moves inside
bump-my-version's own commit and uv verifies it before the commit lands. Every open question above
resolved on the way:

- commit atomicity → (a), the anchored pattern exists and bump-my-version takes it as a multi-line
  basic string; the safety check passed (measured: `uv lock --check` and `uv sync --locked` both
  accept the rewritten lock).
- call sites → `_bump`, so `version.bump` standalone and both `gitflow.py` starts are covered.
- single-writer → `version.py` writes the version field, which is its row of the table; it never
  runs `uv lock`. The rule text now says so.
- group with no python member → `_resolve_project` already errors; a repo with no `uv.lock` gets no
  entry and no hook; a workspace member's version is rewritten in the root lock.

Decision and pitfalls → `contributing/versioning.md` ("`uv.lock` moves with the bump") and
`contributing/task-module-conventions.md` (single-writer rules). The regression the plan asked for →
`tests/integration/test_version_integration.py`, single project and workspace member, against a real
`uv lock`. Nothing deliberately left out.

## Context

The other way `uv.lock` reaches a state a plain `uv lock` will not fix — a workspace member that
moved — landed as a detect-and-instruct hint in `deps.lock` (see README's venv/deps section). Same
file, different cause.

Extracted from the now-retired `plans/2026-08-19-release-management.md`'s
`## Known follow-up (2026-08-20)` section during the now-retired plan-retirement pass — it was live
unfinished work sitting inside a file marked `landed`, so it needed a home with a status field of
its own before that file could be deleted. That plan's landed design now lives in
[`contributing/release-flow.md`](../contributing/release-flow.md) and
[`contributing/versioning.md`](../contributing/versioning.md).

[astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643): `uv sync --locked` (and
`--no-install-project`) fails when _only_ the project's own version changed in `pyproject.toml` with
no dependency change, because `uv.lock` embeds that version too.

`version.py`'s `bump` writes the new version via `bump-my-version` and never re-runs `uv lock`, so a
bump commit leaves `uv.lock` stale. Confirmed still true 2026-08-23:
`rg 'lock' src/repo_tasks/version.py
src/repo_tasks/gitflow.py` returns nothing.

Nothing surfaces this at bump time. It surfaces later, as a `venv.sync` failure on a tree that looks
clean — and `venv.py` deliberately passes `--locked` everywhere precisely so staleness fails loudly
([`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)'s "Never
silently mutate state for convenience"), so the very discipline that makes the repo safe is what
turns this into a confusing failure for whoever pulls next.

Not urgent in the sense that nothing is broken today — this repo hasn't cut a real release through
`version.bump` yet. It becomes a first-release-day problem the moment it does.

## Open questions

The obvious framing ("just run `deps.lock` after the bump") doesn't survive contact with how the
bump actually works, which is what makes this worth a plan rather than a one-line fix.

[NEEDS CLARIFICATION: `_bumpversion_config` sets `commit = true`, so **bump-my-version makes the
commit itself** — the version write and the commit are one step this code doesn't sit between.
Re-locking afterward therefore lands `uv.lock` in a _second_ commit, which is exactly the drift the
original note wanted to avoid ("the commit that changes the version and the commit that re-locks
never drift apart"). Three ways out, none obviously right: (a) add `uv.lock` to
`[[tool.bumpversion.files]]` so bump-my-version rewrites it in the same commit; (b) switch to
`commit = false` and have `version.py` own the `git add`/`git commit` after running `uv lock`; (c)
accept two commits and make them atomic at a higher level (`gitflow.py` squashes, or the pair is
only ever created together). (b) takes commit-construction away from the tool that currently owns it
end-to-end, which the existing design was deliberate about.]

[NEEDS CLARIFICATION: option (a) above looks cheapest but may be unsafe. `uv.lock` stores the
project version as a bare `version = "X.Y.Z"` inside its own `[[package]]` block — identical in form
to every dependency's. Today `rg -c 'version = "0.1.0"' uv.lock` happens to return 1, but that is
luck: any dependency pinned at the same version as this project would collide, and bump-my-version's
search/replace has no notion of TOML structure. Is there a search pattern anchored enough to be safe
(e.g. multi-line, including the preceding `name = "repo-tasks"`), and does bump-my-version support
it?]

[NEEDS CLARIFICATION: which call sites need this? `bump` is invocable standalone (a plain point
release with no gitflow ceremony) _and_ from `gitflow.py`'s `release_start`/`hotfix_start` with
`tag=False`. If the fix lives in `_bump` it covers both; if it lives in `gitflow.py` the standalone
path stays broken. The original note hedged between "`_bump` (or `bump`'s caller in `gitflow.py`)" —
that ambiguity should be resolved, and `_bump` looks right for exactly this reason.]

[NEEDS CLARIFICATION: does this belong to `version.py` at all, given the single-writer rule
([`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md)) makes
`deps.lock` **the only task in the whole package that ever runs `uv lock`**? Calling `deps.lock`
from `version.py` honors that single-writer rule; shelling out to `uv lock` directly from
`version.py` would quietly break it. Cross-module task calls exist already (`dev_env.py` composes
siblings via `pre=[...]`), but that is composition at the task level, not a mid-task call.]

[NEEDS CLARIFICATION: a group bump can span a python project _and_ a Helm chart — `helm.py` and the
chart fields in the group bump landed 2026-08-23. Only the python half has a lock file. Does the
re-lock step run once per group, once per python project in the group, or is it skipped entirely for
a group with no python member?]

## Recommended direction

Rough, not designed. Lean toward fixing it in `_bump` (covers both call sites), invoking `deps.lock`
rather than a raw `uv lock` (preserves the single-writer rule), and resolving the commit-atomicity
question in favor of whichever of (a)/(b) survives the safety check on `uv.lock` search/replace —
with a real preference for (a) if a sufficiently anchored pattern exists, since it keeps commit
construction inside bump-my-version where the current design put it.

Whatever lands needs a regression test that reproduces the actual failure, not just the fix. The
shape is already known and was exercised by hand once: bump `pyproject.toml`'s version with no
dependency change and no relock, then run `venv.sync` and watch `--locked` correctly reject it.

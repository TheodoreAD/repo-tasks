---
status: landed
updated: 2026-09-06
source_repo: github.com-personal/power-user-linux-setup
source_session: 245a4cb0-8e05-451d-9bcc-501922241f86.jsonl
source_moment: 2026-09-06T00:17:43+03:00
---

# `docs.build`'s docstring argues for a placement the same package no longer uses

## Context

`repo_tasks/docs.py`'s `build` opens with two sentences that were true when they were written and
are both false in the package that ships them:

```
In `quality.check`, because `--strict` is the only check in this family that sees a dangling
anchor: `link_check` strips the fragment by design, so a renamed heading passes it. That gap
shipped a red Pages deploy twice in one consumer while `CI` stayed green on both commits.
```

`quality.py` has `precommit` as `pre=[fix, *_CHECKS, docs_build]` and `check` as `pre=[*_CHECKS]`,
so the build is in `precommit` only — and `check`'s and `precommit`'s own docstrings both say so
correctly and at length. `link_check` no longer strips the fragment either: `_bad_link` takes an
`anchors_of` callable and resolves the fragment against the union of `_toc_slug` and `_gh_slug`,
with a `get_close_matches` hint, and `link_check`'s docstring describes that behaviour.

So one module in the package documents a decision the rest of the package reversed, and cites a
limitation the same module removed. The three docstrings were fixed in the same window; this one was
not, which is what makes it the kind of drift a reader trusts.

## Evidence

Found 2026-09-06 while retiring `power-user-linux-setup`'s
`plans/2026-09-04-docs-build-gate-verification.md`, whose whole subject was this divergence — that
plan was filed for `repo-tasks` saying `check`, revised in the filing repo to `precommit` after the
fact, and implemented from the stale copy. The placement was then corrected here the same night
(`7a41c1e`, "Move the docs build out of check, which must not mutate"), which is why every other
docstring reads correctly.

Read directly, not inferred, at two points:

- `power-user-linux-setup/.venv/.../repo_tasks/docs.py:279-281` — the pinned revision that repo
  resolves, `7bb880b`.
- `repo-tasks/src/repo_tasks/docs.py:279-280` on the local clone at `5f067ce` — same text, so it is
  live on `main` rather than an artefact of the consumer's pin.

The `link_check` behaviour it denies is at `docs.py:113-196` (`_anchors`, `_toc_slug`, `_gh_slug`,
`_bad_link`) in both.

## Open questions

**Answered 2026-09-06: no second place.** `rg -n 'docs.build|docs_build|zensical'` over `README.md`,
`contributing/`, `docs.py` and `quality.py` returns `quality.py:245` and `:260` (both correct),
`quality-gate.md:258` and `:270` (both correct, and `:270` quotes the user's own words settling it),
and `docs.py`'s module docstring at `:5`, which says "in the gate" rather than naming a composite
and is therefore right either way. `docs.py`'s `build` at `:279-281` was the only wrong text in the
package.

## Recommended direction

Rewrite `build`'s opening two sentences to say where it actually is and why, without restating the
argument `quality.precommit`'s docstring already carries in full — a pointer there rather than a
second copy, since a second copy is exactly how this drifted. What is worth keeping from the old
text is the fact the twice-red deploy establishes: a renderer sees a class of breakage the rest of
the gate does not, which is the reason the step exists at all.

Worth stating in the replacement, because it is the honest current division of labour: `link_check`
now catches the dangling anchor, covers every tracked `.md` rather than only `docs_dir`, needs no
zensical and writes nothing — so the docs build is defence in depth behind it, not the sole
detector. That is a weaker justification than the original one, and saying so is better than leaving
a stronger claim standing that the code contradicts.

## Migrated to

Landed 2026-09-06, exactly as recommended.

- **The fix**: `src/repo_tasks/docs.py`'s `build` docstring, rewritten to name `precommit`, point at
  `quality.precommit`'s docstring rather than restate its argument, and state the weaker
  division-of-labour justification.
- **Design rationale**: `contributing/task-module-conventions.md`, "A decision lives in one
  docstring; the others point at it" — the transferable half, which is not that this paragraph was
  wrong but that the paragraph holding a second copy of an argument is the one that drifts, and it
  drifted in both its claims while three sibling docstrings stayed correct.

**Deliberately not migrated**: the survey answering this plan's open question (a grep, re-runnable
in seconds, and its answer is now the state of the tree), and the two file:line citations of the old
text, which are what `git show` is for.

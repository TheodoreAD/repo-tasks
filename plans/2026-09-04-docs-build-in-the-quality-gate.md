---
status: landed
updated: 2026-09-04
source_repo: github.com-personal/power-user-linux-setup
source_session: bc30285c-145c-494d-b2d1-be6b37cd37f1.jsonl
source_moment: 2026-09-04T13:05:21+03:00
---

# `docs.build` belongs in `quality.check`'s pre-chain, guarded for repos with no docs site

## Context

`quality.check` already gates `docs.link_check`, and `docs.link_check` cannot see a dangling anchor:
`_broken_link` strips the fragment and its own docstring says so — "`file.md#heading` verifies the
file, never the heading, so a renamed heading still passes". `zensical build --strict` is the only
check in the family that sees one, and it is not in any gate.

That gap has now shipped a red deploy twice in `power-user-linux-setup`. A heading rename in
`docs/claude-code.md` (`e7b481e`) changed its anchor while `docs/index.md:63` kept linking to the
old one; `CI` passed green on `2a4de19` and on `ae59318` while `Deploy docs to GitHub Pages` failed
on both, so `master` moved twice with the published site serving the last good build. The full
account, and the decision this plan implements, is that repo's
`plans/2026-09-04-precommit-does-not-build-the-docs.md`.

Filed rather than implemented because the change is in this repo and the session was working in
`power-user-linux-setup`.

## Evidence

Measured in `power-user-linux-setup` on 2026-09-04, 41 docs pages, warm venv:

- `inv docs.build` — 1.54 s and 1.59 s wall (`zensical` reports 1.20–1.25 s of that). There is no
  cold/warm split to measure: `build` carries `pre=[clean]`, so every run is a full rebuild.
- `inv quality.precommit` — 6.76 s wall, 551 tests. So the addition is +23% on the gate, ~1.5 s in
  absolute terms — well under what makes a session reach for `| tail`.

`docs.link_check` exits 0 on the dangling anchor; `zensical build --strict` exits 1 with
`anchor does not exist … Aborted because --strict flag is set`. No overlap, no cheaper substitute.

## The design question this has to answer

`docs.py`'s own module docstring is the obstacle, and it is deliberate: "Assumes the consumer's
`docs` uv dependency group is installed (`uv sync --group docs`) — `zensical` itself isn't a
dependency of this package. `link_check` is the exception: it needs no zensical, no dependency at
all, and runs in the gate."

Putting `build` in `check` therefore makes the shared gate depend on a tool the shared package does
not declare, on repos that may have no docs site at all. Both halves of the family are real:
`scaffoldapy`'s template makes `mkdocs.yml` conditional on `with_docs`, and among the checkouts on
this machine `creative-writing`, `mkdocs-taudelta`, `mktd` and `power-user-linux-setup` have one
while the rest do not.

Per the family convention, the fix is graceful degradation in the shared logic rather than per-repo
exemption — the shape `shell_check` already uses to no-op on a repo with zero `.sh` files.

## Recommended direction

1. Give `build` (or a gate-only sibling) the guard: no `mkdocs.yml` in the repo root → print and
   return, exactly as `link_check` no-ops on a repo with no markdown. Decide whether the guard lives
   in `build` itself or in a `_docs_build_if_configured` wrapper that `check` uses, so
   `inv docs.build` typed by hand on a docs-less repo still fails loudly rather than lying.
2. Where `mkdocs.yml` does exist, `require_tool("zensical")` so the failure names the missing
   dependency group instead of surfacing as a shell `command not found`.
3. Add it to `check`'s `pre=` list, not to `precommit`'s. `precommit` is `pre=[fix, check]`, so
   `check` reaches both — and only `check` reaches CI, which is what turns the Pages failure into a
   failure of the run people already watch.
4. Update `check`'s docstring: it says "every check, no changes written", and this one writes
   `site/`. True enough that it needs a sentence — `site/` is gitignored in every consumer and
   `build` cleans on entry rather than on exit, so nothing tracked moves and nothing accumulates
   across runs.

## Landed, 2026-09-04

All four steps, with one of them decided against the plan's own suggestion.

1. **The guard lives in `build` itself**, not in a wrapper. The plan left this open, worrying that
   `inv docs.build` on a docs-less repo would then "lie". It does not: `docs.clean` in the same
   module already prints `site/ not present — nothing to clean` and returns, "no mkdocs.yml —
   nothing to build" is a true statement rather than a silent success, and the repo's own
   task-module conventions call for no-opping cleanly when an artifact kind is absent. A second task
   would also have to be published to be debuggable, at which point the gate has a task nobody would
   type.
2. **Not `require_tool`**, which is where the plan's step 2 would have misled a consumer — see the
   pitfall in `contributing/quality-gate.md`. `docs.py` carries `_require_zensical`, naming
   `uv sync --group docs`.
3. `docs_build` in `check`'s `pre=`, aliased on import for the same reason `deps.check` is: `build`
   alone in a gate chain says nothing about what is being built.
4. `check`'s docstring now states the `site/` exception and why it is harmless.

Verified rather than assumed: `inv docs.build` in this repo, which has no `mkdocs.yml`, prints the
no-op and runs nothing. Five new unit tests — the command string still built when a config exists,
the no-op when it does not, the hard stop when a config exists and zensical does not (asserting the
message names the docs group and _not_ the dev group or the quality manifest), and both halves of
the wiring: `docs.build` in `check.pre`, absent from `precommit.pre`. Gate green, 557 tests.

## Open questions

**Answered 2026-09-04, and both halves of the question's premise had gone stale.**

`power-user-linux-setup` **does** have a `docs` dependency group now — `docs = ["zensical==0.0.44"]`
in its `pyproject.toml`, with a comment saying it exists because `repo_tasks`' `docs.py` already
assumes `uv sync --group docs`. The `requirements-docs.txt` this plan describes is gone. The
consumer-side prerequisite it worried about was tracked in that repo's own plan and has since been
done, so nothing here is waiting on it.

The other three repos are the bigger correction: `creative-writing`, `mkdocs-taudelta` and `mktd`
each have an `mkdocs.yml` and **none of them is a repo-tasks consumer** — no `repo-tasks` dependency
in any of their `pyproject.toml` files, and the first two are old poetry-era `mkdocs-material`
projects. They never run `quality.check`, so they were never in scope. The question counted
docs-carrying _checkouts_ when the set that matters is docs-carrying _consumers_, and that set has
exactly one member, which is already correct.

[PITFALL: so the guard is not what protects the docs-carrying consumer — that one is fine either
way. It protects the **many consumers with no docs site**, which is the majority and includes
`repo-tasks` itself. Worth stating because the plan was written as though the risky case were the
repo with docs, and it is the opposite.]

## Migrated to

- [`../contributing/quality-gate.md`](../contributing/quality-gate.md), "In the gate" — the three
  decisions and the pitfall, in the section that already explains every other gate step. The pitfall
  is the one that had to be written down: nothing in the code says why this single step preflights
  differently from all the others, so without it the next reader tidies `_require_zensical` into
  `require_tool` and quietly starts telling consumers to sync the wrong dependency group.
- `src/repo_tasks/docs.py` and `src/repo_tasks/quality.py` — the no-op contract and the `site/`
  exception are stated in the docstrings a reader of those tasks actually reaches.
- The **cross-repo verification this plan still owes** is filed as `power-user-linux-setup`'s
  `2026-09-04-docs-build-gate-verification.md`. This plan carries `source_repo`, and `plan-docs` is
  explicit that such a plan is not done until the original repro is re-checked in the repo where it
  happened — `repo-tasks` has no docs site, so the anchor case cannot be reproduced here at all.
  Filed rather than done, since it is that repo's tree.

**Deliberately not migrated.** The timing measurements (1.54 s on 41 pages, +23% on a 6.8 s gate)
are kept only as the one-line cost in the decision, not as a table: they were taken to answer "is
this affordable in the gate", that question is answered, and a wall-clock number for one site on one
machine ages badly. The blow-by-blow of which commits went out red is in the consumer's own plan and
is not this repo's record to keep a second copy of.

---
status: idea
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

## Open questions

[NEEDS CLARIFICATION: does every docs-carrying consumer already have a `docs` dependency group?
`power-user-linux-setup` does not — its `zensical==0.0.44` lives in a `requirements-docs.txt` the
Pages workflow `pip install`s, plus a machine-wide `uv tool` install, so its
`.github/ci-bootstrap.sh` (`uv run inv dev-env.setup`) would give CI no zensical at all. That
consumer-side prerequisite is tracked in its own plan; check the other three before assuming the
guard alone is enough.]

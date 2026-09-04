---
status: landed
updated: 2026-09-05
source_repo: github.com-personal/power-user-linux-setup
source_session: bc30285c-145c-494d-b2d1-be6b37cd37f1.jsonl
source_moment: 2026-09-04T23:52:51+03:00
---

# `docs.build` shipped into `check` from a plan that had already been superseded

## Context

`c296ad8` landed `docs_build` in `quality.check`'s pre-chain and retired
`plans/2026-09-04-docs-build-in-the-quality-gate.md`. That plan was filed **from**
`power-user-linux-setup`, and its `check` placement was revised there hours before the
implementation landed — the revision never reached the filed copy, so the implementation is faithful
to an artefact that had already been withdrawn.

Not a defect in the implementation, which does exactly what its plan said. The two repos now hold
opposite answers while each believes the question settled, which is the thing worth fixing.

## The chain

1. `power-user-linux-setup` filed the plan saying **`check`**, on this session's own reasoning:
   `precommit` is `pre=[fix, check]`, so `check` reaches both, and only `check` reaches CI.
2. The user overturned it there the same day — _"in theory, docs.build should be in apply, check
   shouldn't mutate. not sure how we can do check without comparison, though"_, and after the
   research, _"i agree with docs build in precommit"_. Written up as the "Revision" section of
   `plans/2026-09-04-precommit-does-not-build-the-docs.md`.
3. That session flagged twice, in its reports, that the filed copy still said `check` and was in
   `repo-tasks`' tree rather than its own — but a filed plan is a snapshot, and nothing carries a
   correction to one that has already been absorbed.
4. `repo-tasks` implemented and retired it.

So `check`'s docstring now argues "it is in `check` rather than in `precommit` because only `check`
reaches CI, and CI is the run people already watch" — which is verbatim the argument the revision
answered.

## What the revision found

**`check` must not mutate.** The gitignore argument the original decision leaned on is the weak
form; the strong one is that `check` is the read-only, CI-style half by construction — safe to run
concurrently, on a read-only checkout, twice with the same answer. Building 3.3 MB into the working
tree from a task documented as "no changes written" is a category error whatever git thinks of the
output.

**The community treats validate and build as separate modes**, checked against primary docs rather
than inferred: Zola ships `zola check`, which builds every page "without writing any of the results
to disk"; Sphinx ships `-b dummy`, which "produces no output. The input is only parsed and checked
for consistency", documented as the linting builder; Hugo has `--renderToMemory` plus a destination
flag.

**Zensical can do none of it, probed rather than assumed** (0.0.44, 2026-09-04). `zensical build`
takes only `-f/--config-file`, `-c/--clean`, `-s/--strict` — no output directory at all, where
MkDocs at least has `-d/--site-dir`. An absolute out-of-tree `site_dir` in an alternate config
passes validation and then **panics**: `invariant: Format(Path(RootDir))` at
`crates/zensical/src/workflow.rs:238`. A relative one works but still writes inside the repo. And
the alternate config must sit in the repo root regardless, since `project_root` is
`os.path.dirname(config_path)`. So the achievable property is "leaves no net change", never "writes
nothing".

**The comparison shape does not rescue it either.** Regenerate-and-fail-on-diff works for a
committed output (`catalog.render-tasks`); `site/` is deliberately gitignored, so there is nothing
to diff against, and committing a build output to manufacture a comparison target is a worse trade
than the one being avoided.

**CI was solved a different way.** `power-user-linux-setup` gave `ci.yml` its own `docs` job on
`push` **and** `pull_request` (`08b1758`), so the docs build reaches CI without `check` carrying it
— and `inv ci.status`, wired the same day, surfaces a Pages failure from the terminal, which was the
original complaint about relying on the deploy workflow.

## The counter-argument, which is why this is a question and not a revert

[PITFALL: **the CI argument is genuinely stronger for other consumers.** A `scaffoldapy`-generated
repo with a docs site and no docs CI job of its own gets its only CI coverage from `check`, and
telling every such consumer to add a job is a real cost the `check` placement does not impose. The
counter is that `check` mutating breaks its documented contract for every consumer, including the
majority that have no docs site at all and gain nothing. Both readings are defensible. What is not
defensible is the current state, where the two repos hold opposite answers and both plans are
retired or landed.]

## Recommended direction

1. **Decide the placement once, in this repo, since this repo owns the shared gate.** Either move
   `docs_build` from `check`'s pre-chain to `precommit`'s (`pre=[fix, check, docs_build]`) and let
   consumers add a docs CI job, or keep it in `check` and amend the "no changes written" contract in
   `check`'s own docstring to say so as a deliberate carve-out rather than an exception in passing.
2. Whichever wins, **say it in the docstring against the argument it beat**, because the losing
   argument is written down in two repos and will otherwise be re-derived.
3. `power-user-linux-setup` is deliberately pinned at `cef6894`, which predates `c296ad8`, so its
   `quality.check` does not yet build docs. Its own
   `plans/2026-09-04-docs-build-gate-verification.md` is blocked on this decision — taking the newer
   pin is what adopts the placement.

~~Whether any other consumer has already taken the newer pin and is now running a mutating
`check`.~~ **Answered by bounding it rather than by enumerating consumers, 2026-09-05.** The
mutating `check` existed on `main` for under an hour — `c296ad8` to `7a41c1e` — and a consumer
installs the revision its own lock names rather than whatever `main` is, so picking it up needed a
re-lock inside that window. `power-user-linux-setup` declares
`repo-tasks = { git = "https://github.com/TheodoreAD/repo-tasks" }` with the revision pinned in its
lock, and that lock predates the commit.

The impact would not have justified the enumeration anyway: the worst case is a gitignored `site/`
written during one `check` run, self-correcting on the next pull. Recorded this way deliberately —
the reason to chase every consumer would have been a bad _outcome_, and there isn't one; chasing it
for tidiness would have cost more than the finding is worth.

## Decided and fixed, 2026-09-05

**Direction 1, in favour of `precommit`** — `pre=[fix, check, docs_build]`. Not re-decided here so
much as applied: the user had already settled it in the repo that filed the plan, and the reason
this repo held the opposite answer was purely that a filed plan is a snapshot. Where a genuine
judgement was needed it was on whether to treat that as settled or reopen it, and the counter-cost
this plan raises — a consumer with a docs site and no docs CI job of its own now needs one — is a
real price rather than a reason to overturn the call.

Direction 2 taken as written: `precommit`'s docstring states the losing argument alongside the
winning one, since the loser is the intuitive one and is written down in two repos. The same is in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md), together with the zensical
probe and the community's separate validate modes, so neither gets re-derived.

Direction 3 is that repo's to take: nothing here changes its pin.

## Migrated to

- [`../contributing/quality-gate.md`](../contributing/quality-gate.md), "In the gate" — the
  placement decision with the user's own words, the zensical probe at 0.0.44 (no output directory,
  out-of-tree `site_dir` panics), the Zola/Sphinx/Hugo validate-mode prior art, and the
  counter-argument as a pitfall.
- `src/repo_tasks/quality.py` — `precommit`'s docstring carries the same, where a reader of the task
  reaches it; `check`'s now says "no changes written" is literal and load-bearing rather than
  carrying a carve-out.

[PITFALL: the chain that produced this is worth keeping as a property of the filing mechanism, not
as a one-off, and is recorded in `quality-gate.md` for that reason. **A filed plan is a snapshot,
and the repo that filed it can move on without the copy knowing.** The filing session flagged twice
in its own reports that the copy was stale, and that was not enough, because the correction had
nowhere to land: the plan had already been absorbed and retired. Nothing in the convention carries
an amendment to an absorbed plan.]

**Deliberately not migrated.** The blow-by-blow of which session did what in which order: it is the
evidence for the pitfall above, and the pitfall is what a future reader needs.

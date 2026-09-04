---
status: idea
updated: 2026-09-01
---

# A shared "generate docs" step, early in `quality.precommit`

## Context

Filed from `power-user-linux-setup`, which has the concrete instance but cannot fix the shared
mechanism: `quality.precommit` is composed in this repo's `quality.py`, and consumer repos get it
through `Collection.from_module(quality)`.

That repo generates part of a docs page from a Python constant — `docs/dev-container.md`'s tag table
is rendered from `CONTAINER_EXCLUDE_TAGS` in `tasks/devcontainer.py`, written into a marker block by
`util.ensure_block`, via an invoke task `inv devcontainer.render-docs`. Nothing ran that task
automatically, so the page could drift from the constant. The gap had been filled by a CI job that
ran the generator and committed the result back to `master` with `git-auto-commit-action`. That job
was deleted 2026-09-01.

The rule that replaced it, now in `~/AGENTS.md`'s "Regenerating a file from a canonical source", is
the user's own wording:

> docs generation/regeneration must be a task, ideally invoke if possible, that may produce changes
> only on the dev machine, before ci. this task must be run as part of the precommit chain, ideally
> early to allow linters and formatters to do their work... we do NOT want anything to autocommit on
> our feature, release, support, develop, main/master or any other non-throwaway, non-source-code
> branch.

So the mechanism has to live here, because every repo in the family needs the same one and the
ordering constraint ("early") is a property of the shared chain, not of any consumer.

[PITFALL: this reads as a reversal of the `~/AGENTS.md` rule it now sits inside, which says
regeneration is "never auto-wired into routine `fix`/`check`/`precommit` runs". It is not. That
sentence is about **pulling** a file from outside the repo — its recorded evidence is
`inv configs.pull` dragging this repo's `pytest.ini` into `scaffoldapy` — where the hazard is an
upstream bump nobody chose. **Generating** from the repo's own code has no upstream: the generator
and its output land in the same commit. Both rules now live in that section with the distinction
stated; don't collapse them again.]

## Open questions

[NEEDS CLARIFICATION: what is the generator contract? A consumer repo has to declare _what_ to run.
Candidates: a well-known task name the chain calls if it exists (`docs.generate` in the consumer's
own namespace, skipped silently when absent); a list in `pyproject.toml`'s tool config; or a `pre=`
chain the consumer assembles itself. The first keeps consumer repos from composing anything — which
is the family convention for shared tooling — but "call it if it exists" needs a way to ask invoke
whether a task exists without importing the consumer's namespace twice.]

[NEEDS CLARIFICATION: where exactly in the chain? "Early, before the linters and formatters" is the
stated intent, and the reason is real — `power-user-linux-setup`'s generated block is pre-padded to
dprint's own table style precisely because the two would otherwise disagree forever about the
"idempotent" output (see the comment on `_tag_table()` there). Running the generator first and
letting `dprint fmt` format its output removes that whole class of problem, and would let that
pre-padding be deleted. But it also means the generator runs on every `inv quality.fix`, including
runs that touch nothing it reads.]

[NEEDS CLARIFICATION: does `check` (the CI half) run the generator too, and fail on a diff? That is
the enforcement the deleted auto-commit job was standing in for, and without it a contributor who
skips the gate still ships drift. The argument against is that it makes `quality.check` non-read-
only unless it generates into a temp location and compares.]

[NEEDS CLARIFICATION: is `docs` the right namespace? `repo_tasks.docs` already exists and is
published into consumers as its own collection. If the task lands there it is `inv docs.generate`,
which reads well but sits beside whatever that module does today.]

## Recommended direction

Add the step to the `fix` half of the chain, ahead of the formatters, gated on the consumer actually
declaring a generator — a repo with nothing to generate must no-op cleanly rather than be exempted,
per the family convention that the shared composite is mandatory and identical and degrades
gracefully instead of being opted out of.

Pair it with a `check`-side verification that fails on a diff, since the whole point is that CI
stops being the thing that fixes drift. Prove it against `power-user-linux-setup` first — it is the
repo with a real generator, and its `_tag_table()` pre-padding is a measurable before/after: if the
ordering is right, that workaround can be deleted and the output stays stable across
`inv quality.fix` runs.

[DEFERRED: `power-user-linux-setup` currently has no automatic drift protection at all, between the
CI job being deleted and this landing. A unit test asserting the rendered block matches the file
would cover it in the meantime, in that repo, at no cost to this one.]

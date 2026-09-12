---
status: in-progress
updated: 2026-09-12
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

## The mechanism landed for this repo's own blocks (2026-09-12)

`5ed82c5`. `docs.generate` renders each block into the marked region of its file;
`docs.generate-check` fails when one has drifted. The first block is the task-requirements table in
`README.md` — every task needing network, Docker or an authenticated `gh`, read from the `@requires`
declarations and, for a composite, from its chain. It exists because
`contributing/task-module-conventions.md` settled that a composite's requirements are computed
rather than restated, which left nobody able to _read_ them.

Three of the four questions below are answered by what shipped, and the answers held up against a
real formatter rather than in the abstract:

- **Where in the chain:** first in `fix`, ahead of the linters and formatters, as the direction
  said. The renderer emits plain markdown and `dprint` owns the layout.
- **Does `check` run it and fail on a diff:** yes, `docs.generate-check` sits in `_CHECKS`. It
  writes nothing and needs no temp file — it renders in memory and compares — so the read-only
  contract of that half is intact.
- **Namespace:** `docs.generate` and `docs.generate-check`. The second name matters beyond
  readability: `<ns>.*-check` is auto-approved as read-only by this machine's agent allowlist, so a
  check half that mutated would run unprompted.

[PITFALL: **the comparison is where the whole ordering argument actually lives, and whitespace is
only half of it.** `dprint` aligns table pipes _and_ pads the delimiter row to the column width, so
a rendering never matches the formatted file byte-for-byte. Normalizing whitespace alone still
failed, on the dashes — found by running it rather than by reasoning about it. Both halves now
normalize whitespace and dash runs, and **`generate` uses that comparison too**, which is the
sharper case: a byte comparison would rewrite the block on every run, the formatter would re-align
it, and the file would show as modified after every `inv quality.fix` forever. That is the
oscillation this ordering exists to remove, reintroduced by the generator instead of by the
renderer's padding. Verified by running `fix` twice and diffing: the second run changes nothing.]

**The marker is the opt-in, and that is the contract for a block this package owns.** A file without
markers is skipped in silence, so a consumer repo pays a no-op rather than being exempted — the
family rule for a shared composite. A consumer that wanted the same table would paste the markers
into its own README and get it.

## Open questions

[NEEDS CLARIFICATION: what is the generator contract **for a consumer's own generator**? This is the
one question the landed mechanism does not answer: it covers blocks rendered from _this package's_
code, where the renderer ships alongside the chain that calls it. `power-user-linux-setup`'s tag
table is rendered from a constant in its own `tasks/`, and nothing here can call it: `pre=` chains
are composed in this repo, and a repo-tasks task cannot see the consumer's namespace. The candidates
are unchanged — a well-known task name invoked as a subprocess, or a list in `repo-tasks.toml`,
which is the consumer config schema that already exists. That repo is the test case, and it is now
the only thing between the mechanism and the problem that prompted it.]

~~Where exactly in the chain?~~ **First in `fix`**, and the pre-padding it was weighed against can
indeed be deleted — the generator emits plain markdown and `dprint` formats it like anything else.
The objection that it then runs on every `inv quality.fix` including runs that touch nothing it
reads is real and costs nothing measurable: rendering is pure introspection, and the comparison
means an unchanged block is not even written.

~~Does `check` run the generator too, and fail on a diff?~~ **Yes**, and the argument against it
dissolved on contact: `docs.generate-check` renders in memory and compares, so it needs neither a
temp location nor a write, and `quality.check` stays read-only.

~~Is `docs` the right namespace?~~ **Yes** — `inv docs.generate` and `inv docs.generate-check`,
which also satisfies the allowlist convention that a `*-check` name never mutates.

## Recommended direction

~~Add the step to the `fix` half of the chain, ahead of the formatters~~ — done, `5ed82c5`. The
"gated on the consumer actually declaring a generator" half became "gated on the file carrying the
markers", which is the same property with nothing to declare.

~~Pair it with a `check`-side verification that fails on a diff~~ — done, same commit.

**What is left is the half this repo cannot test on itself.** The mechanism was proved against a
block rendered from this package's own code, so the ordering argument is settled but the consumer
contract is not: `power-user-linux-setup`'s `_tag_table()` is rendered from a constant in that
repo's own `tasks/`, and reaching it needs the open question above. Its pre-padding is still the
measurable before/after — this repo's equivalent padding was never written, and a second `fix` run
now changes nothing, so the ordering does what it was expected to.

[DEFERRED: `power-user-linux-setup` currently has no automatic drift protection at all, between the
CI job being deleted and this landing. A unit test asserting the rendered block matches the file
would cover it in the meantime, in that repo, at no cost to this one.]

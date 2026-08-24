---
status: landed
updated: 2026-08-25
---

## Migrated to

Landed 2026-08-25, all three defects:

- **1** — `configs.promote --apply` now requires `--file <name>` and writes only that file; a
  print-only run still lists every differing file. Code contract, lives in `tasks.py`.
- **1a** — the ratchet is structurally gone: the shipped `pyrightconfig.json` spells `include` as
  `["src*", "tests*", "tasks*"]`, the one glob shape basedpyright tolerates when nothing matches
  (measured — `tests/**` and `./tests` still exit 3; only a `*` in the last segment escapes), so
  `configs.pull` copies every file verbatim and `_resolve_content` is deleted. Root and package are
  byte-identical for all five files. The measurement and its reach limits are recorded in the
  shipped file's own comment and in `plans/2026-08-19-gitignore-tool-alignment.md`'s audit; a unit
  test pins the glob shape.
- **2** — moot: `examples/sample-service` moved to `tests/fixtures/sample-service` (76ee882), and a
  directory include is recursive, so `tests*` covers it. No `examples` entry needed.

Deliberately not migrated: the "should divergence be a declared `configs.local.toml` override"
question — with nothing left to diverge it has no live case here; it stays tracked as
`power-user-linux-setup`'s `plans/2026-08-14-python-repo-scaffolding.md` §D. The "detect uncovered
`*.py` files" check moved to `plans/2026-08-19-gitignore-tool-alignment.md`, next to the gitignore
check it would share a task with.

## Context

`configs.py` ships this repo's tool configs to every consumer (`configs.pull`/`configs.diff`), and
`configs_promote` in this repo's own `tasks.py` runs the other direction — root → package — once a
root-level tuning is ready for everyone. `configs.py`'s own docstring calls this repo "the one place
root and package are allowed to diverge in-flight", and `pyrightconfig.json` carries a comment
saying the same about its own root-only `exclude`.

Neither direction of that round trip actually represents the divergence, so both lose it. Both
defects were hit live on 2026-08-23 while landing `examples/sample-service`.

### 1. `configs_promote --apply` promotes every differing file, not the one you meant

The task loops `_CONFIG_FILES` and writes root → package for **every** file whose contents differ.
There is no way to promote one file. Promoting a genuinely-shared `dprint.json` change also wrote
this repo's two deliberate, documented root-only divergences into the baseline every consumer
receives:

- `pyrightconfig.json`'s `"exclude": ["tests/integration"]` — this repo's own integration tier,
  which no consumer has.
- `pytest.ini`'s `--ignore=tests/integration` in `addopts` — same tier, same reason.

Caught only because the task prints one line per file it wrote and all three were read. Nothing
failed; the wrong baseline would simply have shipped on the next release. Both were reverted by
hand.

[PITFALL: the two divergent files are exactly the two whose divergence is documented as intentional
in their own comments — so the files most likely to be clobbered are the ones a reader has already
been told not to worry about.]

Confirmed still true after the revert: `ruff.toml`, `dprint.json` and `.editorconfig` match the
package copy byte for byte; `pyrightconfig.json` and `pytest.ini` are the two standing divergences.
Nothing was committed, so no consumer ever received the clobbered baseline — `git log` on both
shipped files shows only the commit that created them.

### 1a. `pull` narrows, `promote` makes the narrowing canonical — a ratchet

The same promote would also have shrunk the shared `include` list, which is a worse failure than the
two excludes above and was missed on the first pass:

```
root    pyrightconfig.json  "include": ["src", "tests",          "tasks.py"]
package pyrightconfig.json  "include": ["src", "tests", "tasks", "tasks.py"]
```

`"tasks"` is absent from the root copy, and that is not a deliberate divergence at all —
`configs.pull`'s `_resolve_content` filters the canonical list to paths that **exist** and writes
the filtered result into root. This repo has no `tasks/` directory, so root legitimately lost the
entry on its last pull. `configs_promote` then copies root → package verbatim, which would have made
the filtered list canonical for everyone.

Consequence, had it been committed: `power-user-linux-setup` — the flat-layout `tasks/` consumer
this entry exists for, named as such in the config's own comment — would silently stop type-checking
that directory on its next `configs.pull`. Silently, because a directory that no include entry names
is simply not part of the project — there is no diagnostic for coverage you never asked for.

[PITFALL: `pull`'s filtering is deliberate and correct on its own (it keeps a consumer's config free
of entries that don't apply to it). It only becomes destructive when composed with `promote`, whose
input is the _filtered_ file rather than the canonical one. Neither task is wrong in isolation;
their composition is.]

### 2. `pyrightconfig.json`'s `include` allowlist silently leaves new source trees unchecked

`include` is the fixed list `["src", "tests", "tasks.py"]`, shared by every consumer. The config's
own comment justifies this by claiming basedpyright "silently no-ops on whichever entries don't
exist" — which is false for a literal path (it hard-errors, exit 3); what actually makes one list
work everywhere is `configs.pull` filtering it per consumer. Either way the cost is the same: source
living outside those entries is silently **not** type-checked, with nothing to notice it.

`examples/sample-service` is the live instance. Measured 2026-08-23: a plain `basedpyright` run
analyses 36 files and reports nothing from `examples/`; pointing it at
`examples/sample-service/src/sample_service/__main__.py` explicitly analyses that file and reports a
warning that the normal gate never sees. `ruff` covers the tree (it walks `.` and respects
`.gitignore`), so the gap is basedpyright-specific and easy to miss — `inv quality.check` passes
either way.

[PITFALL: adding `"examples"` to this repo's root `pyrightconfig.json` does not stick.
`configs.pull`'s `_resolve_content` rewrites the `include` array to the canonical list filtered to
paths that exist, so the next pull drops any locally-added entry. A local fix here is not durable —
only a change to the shipped baseline is.]

## Both divergences are gone (2026-08-24)

Not theory any more — implemented. `pytest.ini`'s `--ignore=tests/integration` became
`testpaths = tests/unit`, and `pyrightconfig.json`'s `tests/integration` exclude was deleted along
with the dependency group that caused it. Root and package are now byte-identical for `pytest.ini`,
and differ for `pyrightconfig.json` only by the `"tasks"` entry that `configs.pull` filters out of
the root copy — i.e. only by defect 1a, which is the mechanism problem rather than a divergence.

So defect 1 has almost nothing left to clobber. It is still worth fixing, because 1a means a promote
of `pyrightconfig.json` would still narrow the canonical include list.

### The reasoning that got there

Direction taken 2026-08-24, after the tool audit in `plans/2026-08-19-gitignore-tool-alignment.md`:
excludes don't belong in tool configs outside `.gitignore` as a default posture, and everything that
isn't a main dependency goes in `dev`.

Follow both through and most of this plan stops applying:

- The `pytest.ini` divergence goes away entirely — the test-tier work (landed, see
  [`contributing/test-tiers.md`](../contributing/test-tiers.md)) replaced
  `--ignore=tests/integration` with `testpaths = tests/unit`, an include rather than an exclude,
  identical for every consumer.
- The `pyrightconfig.json` divergence goes away too, for a different reason: that exclude exists
  only because `tests/integration` can't import without the `integration` dependency group. Move
  `testcontainers` into `dev` and there is nothing to exclude.

With both gone, root and package are byte-identical, defect 1 has nothing left to clobber, and only
the `include`-filtering ratchet (1a) survives as a real mechanism problem.

[PITFALL: 1a does **not** dissolve, and it is the one to keep. It is caused by basedpyright
hard-erroring on a literal `include` path that does not exist — measured, and the reason
`_resolve_content` filters at all. Nothing about dependency groups or the excludes rule touches it.]

Defect 2 is likewise unaffected: `examples/` stays untype-checked whatever happens to the excludes,
because it is an `include` question.

## Open questions

- [NEEDS CLARIFICATION: should `configs_promote` take a file argument (`--file dprint.json`), refuse
  to run when more than one file differs, or print a diff and require confirmation per file? The
  first is the smallest change; the second is closest to how the rest of this package treats
  ambiguity ("ambiguity is an error, not a guess"), and would have failed loudly on the exact case
  that bit here.]
- [NEEDS CLARIFICATION: is "root and package may diverge in-flight" still the right model at all?
  The alternative is to make the divergence explicit and machine-readable — the `configs.local.toml`
  per-repo override that `power-user-linux-setup`'s `plans/2026-08-14-python-repo-scaffolding.md` §D
  already sketched and this package deliberately hasn't built. If that existed, `tests/integration`
  would be a declared local override rather than an undeclared drift, and promote could refuse to
  touch anything covered by one.]
- [NEEDS CLARIFICATION: does `"examples"` belong in the canonical `include` list? It closes the gap
  for every consumer at once, which is the same argument that produced the current list, and it is
  free only because `pull` filters it out where the directory is absent — a _literal_ entry that
  does not exist is a hard config error, so this is not the harmless addition it first looks like.
  Against: speculative for consumers with no `examples/`, and this package's conventions push back
  on adding shared surface for one repo's need. Worth checking what other trees are plausible
  (`scripts/`, `docs/` snippets) before settling on a list rather than adding one entry reactively.
  In its favour: a directory include is **recursive**, measured — a literal `examples` entry does
  reach `examples/sample-service/src/`, so one entry covers every workspace member's nested layout
  with no glob and no exclude.]
- [NEEDS CLARIFICATION: separately from what the list contains — should anything _detect_ the gap? A
  check that every tracked `*.py` file is covered by some `include` entry would have caught this the
  moment `examples/` appeared, and would keep catching it. That is close in spirit to the fixed,
  hard-coded "are the paths our tools depend on actually gitignored" check
  `plans/2026-08-19-gitignore-tool-alignment.md` already proposes, and the two may want to be one
  task rather than two.]

## Recommended direction

Defect 1 first — it is small, self-contained, and the one that can ship a wrong baseline to every
consumer. Make `configs_promote` unable to write a file the caller didn't name, whichever of the
three shapes above wins.

1a needs its own fix and does not go away by naming one file: promoting `pyrightconfig.json`
deliberately would still narrow the list. Promote has to reconcile against the canonical copy rather
than overwrite it — at minimum, never dropping an `include` entry that only failed `pull`'s
existence filter. Until that exists, `pyrightconfig.json` should not be promoted at all.

Defect 2's _mechanism_ question (a real local-override representation) is the larger design and
should not gate the _coverage_ question: whether `examples/` is type-checked at all is answerable on
its own, and the sample service stays unchecked until it is.

Both defects argue the same underlying point, worth settling once rather than per-defect: an
undeclared divergence between root and package is not a workable model for a file that gets
mechanically copied in both directions.

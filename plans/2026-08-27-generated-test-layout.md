---
status: idea
updated: 2026-08-27
depends_on: [scaffoldapy]
---

# The tier split and the socket guard should be generated together

## Context

`repo-tasks` now ships both halves a two-tier test tree needs — `pytest-socket` and `pytest-cov` are
in the `repo-tasks-quality` manifest, so every consumer has them installed — but nothing generates
the tree that uses them. This repo's own `tests/unit/conftest.py` holds the autouse `no_network`
fixture and is explicitly "exemplary by being read, not distributed"
([`contributing/test-tiers.md`](../contributing/test-tiers.md)). Generated projects are
`scaffoldapy`'s half, and today it generates:

- `tests/conftest.py` and `tests/unit/test_<something>.py`, per interface,
- **no** `tests/integration/`,
- **no** socket guard,
- **no** question about the layout at all.

So a generated repo lands on a half-split shape: `tests/unit/` exists because the shipped
`pytest.ini` says `testpaths = tests/unit`, but the second tier the split exists _for_ is absent,
and the unit tier's central promise — "no Docker, no network, nothing outside tmp_path" — is
enforced only in the repo that wrote it down.

The user's framing, 2026-08-27: the split and the guard "would be nice to have together, and created
by default, but if the user prefers a simple `tests/` don't force the pytest socket restriction."

Two facts make that shape cheap to build now:

- **The plugins are already everywhere.** Standardising them (see `test-tiers.md`'s decision) means
  a generated tree opts in with a fixture, never with a dependency edit.
- **A flat `tests/` is a supported layout as of `14a91f3`.** It was not, for a day:
  `filterwarnings
  = error` promoted the `testpaths` fallback's own notice to a hard exit-1 crash,
  so a repo with a plain `tests/` could not run `pytest` at all. That is fixed and covered by a real
  subprocess test, which is what makes "offer the flat layout as a genuine choice" an honest offer
  rather than a second-class path.

## Open questions

[NEEDS CLARIFICATION: whether the layout is a copier **question** or a consequence of an existing
one. A standalone `tests_layout: split | flat` is the obvious shape, but it may be derivable — a
`library` or `skill` interface with `fetch_strategy = none` has nothing to integration-test, while
`web_service` and any `fetch_strategy != none` project does. Deriving it means one fewer prompt;
asking means the generator does not quietly decide something the developer cares about.
`~/AGENTS.md`'s generator guidance — independent combinable axes over a top-level enum, and minimal
necessary prompts — cuts both ways here and does not settle it.]

[NEEDS CLARIFICATION: what a generated `tests/integration/` should actually contain. An empty
directory does not survive git. A placeholder test is the shape `test_politeness.py` and friends
already use, but an integration seed needs something real to integrate with, and the natural
candidate differs per interface (a `TestClient` round trip for `web_service`, a live fetch for
`fetch_strategy != none`, nothing obvious for `library`). The fallback is a `README.md` in the
directory explaining what the tier is for, which costs nothing and keeps the directory tracked.]

[NEEDS CLARIFICATION: whether the flat layout should get the socket guard as an **opt-in comment**
rather than nothing at all. The user's instruction is not to force it; a commented-out fixture with
one line saying what uncommenting buys is not forcing, and it puts the option in front of the person
who would want it. Against: a generated repo full of commented-out code is its own smell.]

[NEEDS CLARIFICATION: whether `test.untested-modules` and the `_integration` suffix convention need
saying in the generated `AGENTS.md`. Both are gate-visible rules a generated repo inherits without
being told — [`2026-08-27-tests-package-layout.md`](2026-08-27-tests-package-layout.md) makes the
same point about the basename-uniqueness rule, and that plan's own `[DEFERRED:]` names this same
generated `tests/` tree. The two should be decided together rather than each editing the template
alone.]

## Recommended direction

Rough, and deliberately not settled — the questions above come first.

1. **Split by default, flat on request.** The split is the shape worth defaulting to: two tiers with
   different prerequisites is what the shipped `pytest.ini` and `test.integration` are built around,
   and a project that discovers it wants an integration tier later should find the seam already cut.
2. **The guard ships with the split, never with the config.** `tests/unit/conftest.py` gets the
   autouse `no_network` fixture (and, worth considering alongside, `isolated_home` — the same
   `Path.home()` trap this repo hit costs a generated project the same stale files). The flat layout
   gets neither, and the shipped `pytest.ini` gains no `--disable-socket`: `addopts` reaches every
   consumer, and the guard is a promise the unit tier makes rather than one the shared config may
   impose on a layout that never made it.
3. **Cover it in the e2e tier.** `scaffoldapy`'s `test_e2e.py` renders every combination and runs
   the generated repo's own gate — that is where "the generated split actually passes its own
   `quality.check`" gets proved, and where a flat-layout combination would prove the fallback works
   end to end rather than only in this repo's subprocess test.

[DEFERRED: this supersedes the narrower deferred item in
[`2026-08-26-quality-tool-gaps.md`](2026-08-26-quality-tool-gaps.md) §13, which assumed seeding the
fixture would be what moved `pytest-socket` into the exported manifest. The manifest move happened
first and on its own merits, so what is left is only the generated tree.]

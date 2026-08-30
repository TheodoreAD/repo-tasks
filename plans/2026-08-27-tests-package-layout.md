---
status: idea
updated: 2026-08-30
---

# The shipped pyrightconfig forbids `tests/` being a package

## Context

Turned up in `ingesta` on 2026-08-27 while building its first real test suite, which wanted a shared
synthetic-world helper in `tests/conftest.py` imported by name from several modules in
`tests/unit/`.

Writing `tests/__init__.py` + `tests/unit/__init__.py` and importing
`from tests.conftest import ...` fails this package's own quality gate:

```
tests/unit/test_bands.py:27:6 - error: Import "tests.conftest" could not be resolved (reportMissingImports)
```

Five such errors, one per importing module. The cause is ours: the shipped `pyrightconfig.json` sets
`executionEnvironments[{"root": "tests"}]`, which makes `tests/` the search root for files beneath
it — so `conftest` resolves and `tests.conftest` cannot. pytest itself collects the packaged layout
fine; only the type checker objects.

The workaround adopted in `ingesta` was to drop the `__init__.py` files and import bare `conftest`.
That works, and it is a layout pytest documents — but it was chosen to satisfy a type checker rather
than on its merits, and it silently takes on a constraint nobody has written down.

### pytest's own guidance is two-sided, and both sides apply here

- [Import modes](https://docs.pytest.org/en/stable/explanation/pythonpath.html), on `prepend` (still
  the default, and what every repo in this family uses): "it is **highly recommended** to arrange
  your test modules as packages by adding `__init__.py` files", because otherwise "each test file
  needs to have a unique name compared to the other test files".
- [Good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html), on
  a `src` layout with tests outside the application package — which is exactly this family's shape:
  `__init__.py` is "just a workaround for the prepend import mode, which should be phased out", and
  leaving them out "should just work".

So the current arrangement is supported, not a mistake. It is the unique-basename requirement that
comes with it, and that requirement is currently invisible.

### We are already relying on it, in this repo

`repo-tasks` runs two tiers and has no `__init__.py` anywhere under `tests/`. Checked 2026-08-27:
zero duplicate `test_*.py` basenames across `tests/unit/` and `tests/integration/`. What maintains
that is the `_integration` suffix on every integration module — `test_version_integration.py`,
`test_clean_os_integration.py`, and so on.

[PITFALL: That suffix is load-bearing for _collection_, not merely descriptive.
`contributing/test-tiers.md` explains at length why the tiers are split and what each `conftest.py`
holds, but never says that a `tests/integration/test_dist.py` alongside `tests/unit/test_dist.py`
would break the run outright. Under `prepend` with no `__init__.py`, two same-named test modules
collide on import. The convention is doing real work and reads as a naming preference.]

A single-tier consumer like `ingesta` cannot hit this today. It gets its second tier at its stage 2,
and the natural name for the new file is the same as the unit one.

### What constrains any fix

- ~~**The config is distributed byte-identically.**~~ **No longer true as of `c514bd9`
  (2026-08-30).** When this plan was written `configs.py`'s `_CONFIG_FILES` materialized
  `pyrightconfig.json` into every consumer verbatim and there was no per-repo parameterization at
  all. `_derive_for_project` now computes two lines per consumer — `pythonVersion` from that repo's
  `requires-python`, and `pytest.ini`'s `anyio_mode` from whether its lock resolves AnyIO — with
  `_diff_config_files` applying the same derivation so `configs.diff` still compares exactly. See
  [`2026-08-29-python-floor-in-the-shipped-configs.md`](2026-08-29-python-floor-in-the-shipped-configs.md).

  This matters to the question below rather than answering it. The rule the family settled on is
  **derivation, never preservation**: a pulled file stays fully determined by the canonical copy
  plus declared facts about the consumer. `extraPaths: ["."]` is not a derived value — it would be
  the same for every consumer — so the mechanism does not apply to it, and the real objection is
  unchanged: whether the entry is correct everywhere, not whether it can vary. What has changed is
  that "the file cannot vary at all" is no longer an argument available to either side.

  This repo's own root copies are still byte-identical to the package copies, verified 2026-08-30 —
  but only because its `requires-python = ">=3.11"` and its lock carries AnyIO, so both derived
  values coincide with the canonical defaults. That coincidence is not the general case and should
  not be read as one.
- **This package ships tool config, never project structure.** `contributing/test-tiers.md` is
  explicit that the tests tree here is "exemplary by being read, not distributed" and that
  `scaffoldapy` owns the generated layout. So this repo can only decide whether the config _permits_
  a packaged `tests/`; whether any repo adopts one is `scaffoldapy`'s call, and a separate
  conversation.

## Recommended direction

Do the cheap, unambiguously-correct half first, and treat the config change as a genuinely open
question rather than a foregone one.

1. ~~**Write the constraint down**, in `contributing/test-tiers.md` next to the conftest layout.~~
   **Landed 2026-08-30** — "Every test module basename must be unique across the whole tree", under
   Conftest layout, carrying the `_integration`-suffix pitfall. Re-checked while writing it: zero
   duplicate `test_*.py` basenames in the tree, and the single `__init__.py` under `tests/` belongs
   to the `sample-service` fixture's own package rather than to the test tree, so the claim is about
   what it says it is about. Worth doing whatever is decided below — it is true today, enforced by
   nothing, and the failure it prevents is a collection error rather than a wrong answer.
2. **Then decide on `extraPaths`,** on its merits, using the questions below.

The mechanical fix, if taken, is one line in the tests execution environment:

```json
"executionEnvironments": [
  {
    "root": "tests",
    "extraPaths": ["."],
```

[UNVERIFIED: `"extraPaths": ["."]` was measured on 2026-08-27 in `ingesta` only — a **single-tier**
repo. With the `__init__.py` files in place it took basedpyright from 5 errors to 0 while pytest
still collected all 128 tests, and both were reverted afterwards. It has not been tried in a
two-tier repo, which is the case that actually motivates the packaged layout, nor against this
repo's own suite.]

## Open questions

[NEEDS CLARIFICATION: Whether `extraPaths: ["."]` costs anything worth caring about. It puts the
repo root on the type checker's search path for files under `tests/`, which is close to the reason
pytest itself dislikes `__init__.py` under `prepend`: prepending the root makes the source package
importable from the tree rather than from the installed distribution, which is exactly what the
`src` layout exists to prevent. Whether that objection transfers to a _type checker's_ search path —
which resolves imports but installs nothing and runs nothing — is the crux, and it is not obvious.
`contributing/type-checking.md`'s reasoning for `include` over `exclude` is the closest precedent
for how this repo thinks about that trade.]

[NEEDS CLARIFICATION: Whether to permit the packaged layout at all, or to keep the current one and
rely on the documented basename rule from step 1. Keeping it is defensible on pytest's own
good-practices page and costs nothing today. Permitting it is what a consumer needs the moment it
wants a genuinely shared test helper imported by name across tiers — the thing `ingesta` was
reaching for.]

[NEEDS CLARIFICATION: If the layout is permitted, whether the `_integration` suffix should stay.
With `__init__.py` files present the collision it prevents cannot happen, so it becomes purely
descriptive — at which point it is a naming preference and can be argued on readability alone.]

[DEFERRED: `scaffoldapy`'s generated `tests/` tree. It omits `__init__.py` today, which is why
`ingesta` started where it did. Whatever is decided here only reaches new projects through that
template, so a decision to permit the packaged layout is incomplete until that repo has had the same
conversation. Not pursued now — the config question comes first, because a template change that the
shared gate rejects is worse than no change.]

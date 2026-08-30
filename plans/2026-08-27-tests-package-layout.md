---
status: landed
updated: 2026-08-30
---

# The shipped pyrightconfig forbids `tests/` being a package

## Migrated to

- [`../contributing/type-checking.md`](../contributing/type-checking.md), "Why `tests/` may not be a
  package" — the `extraPaths` rejection with its reasoning, the four-run measurement table, and the
  pytest-endorsed alternative. Listed in that file's Rejected section too.
- [`../contributing/test-tiers.md`](../contributing/test-tiers.md), Conftest layout — the
  basename-uniqueness rule and the `_integration`-suffix pitfall, landed 2026-08-30 (step 1 of this
  plan), now restated as a standing requirement rather than something a later decision might lift.
- [`2026-08-27-generated-test-layout.md`](2026-08-27-generated-test-layout.md) — the deferred
  `scaffoldapy` half. Its template omits `__init__.py` today, which the decision makes correct
  rather than provisional; what survives is only whether the generated `AGENTS.md` states the
  inherited rules, which is that plan's own subject.

**Not migrated, deliberately:** the pytest documentation quotations (both sides are cited by link in
the two `contributing/` files, and a third copy would be one more thing to keep current), and the
`ingesta` narrative — the repo where this surfaced worked around it by dropping `__init__.py`, which
the decision now endorses, so nothing is owed there.

## What it was

Turned up in `ingesta` on 2026-08-27: a shared synthetic-world helper in `tests/conftest.py`,
imported by name from several modules in `tests/unit/`, failed this package's own gate with
`Import "tests.conftest" could not be resolved` — five errors, one per importing module. The cause
was ours: the shipped `pyrightconfig.json` sets `executionEnvironments[{"root": "tests"}]`, making
`tests/` the search root for files beneath it, so `conftest` resolves and `tests.conftest` cannot.
pytest collected the packaged layout fine; only the type checker objected.

Two questions followed: write the unique-basename constraint down (cheap, unambiguously right), and
decide whether the config should permit a packaged `tests/` at all.

## How it was settled

The first landed 2026-08-30 in `test-tiers.md`.

The second was measured here on 2026-08-30 rather than argued, since the only prior evidence came
from `ingesta` — a **single-tier** repo, which is not the case that motivates a packaged layout.
Four runs, basedpyright 1.39.10, against this repo's two tiers:

| setup                                               | result                                             |
| --------------------------------------------------- | -------------------------------------------------- |
| `extraPaths` alone, unpackaged tree                 | 0 errors — no structural cost on the current shape |
| packaged tree, no `extraPaths`                      | `Import "tests.conftest" could not be resolved`    |
| packaged tree + `extraPaths`                        | 0 errors, all 520 tests still collected            |
| `from src.repo_tasks import version` + `extraPaths` | resolves clean                                     |

The last row decided it, and it is causal: the identical import is a `reportMissingImports` error
with `extraPaths` removed and nothing else changed.

The open question had been whether pytest's objection to prepend-mode `__init__.py` transfers to a
type checker's search path, "which resolves imports but installs nothing and runs nothing". It does,
in a sharper form than expected: `.` on the search path makes `src.<pkg>` a second blessed route to
the same code, and `import src.repo_tasks.version` and `import repo_tasks.version` produce different
module objects with separate state at runtime. The setting is exactly what stops the type checker
flagging that, in a file every consumer inherits, to buy a layout one consumer wanted.

So the answer is no, and the basename rule is the standing requirement rather than a stopgap.

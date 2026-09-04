---
status: in-progress
updated: 2026-09-04
---

# Should `tests/` be a package, and under which import mode?

## Context

Reopened 2026-08-30, the same day the now-retired `plans/2026-08-27-tests-package-layout.md` was
deleted for deciding it (read it back with
`python3 ~/.agents/skills/plan-docs/scripts/plans.py archive --file 2026-08-27-tests-package-layout.md`).
That plan framed the question as two options — permit a packaged `tests/` via `extraPaths: ["."]`,
or keep the current unpackaged tree and its basename rule — and chose the second. **The framing was
wrong: pytest documents three, and the retired plan's write-up made one claim that is simply
false.**

The false claim, now corrected in
[`../contributing/type-checking.md`](../contributing/type-checking.md): that the basename-uniqueness
requirement is a **standing** one that "nothing will make impossible later". One line of config
makes it impossible — `--import-mode=importlib` — and pytest says so directly.

Everything below is measured or quoted, not recalled.

## The three options pytest actually documents

`prepend` is the default and is staying that way. From
[Import modes](https://docs.pytest.org/en/stable/explanation/pythonpath.html): _"Initially we
intended to make `importlib` the default in future releases, however it is clear now that it has its
own set of drawbacks so the default will remain `prepend` for the foreseeable future."_

| option                              | shared test helper            | unique basenames | basedpyright                     |
| ----------------------------------- | ----------------------------- | ---------------- | -------------------------------- |
| `prepend`, no `__init__.py` (today) | bare `import conftest` only   | **required**     | clean                            |
| `prepend` + `__init__.py`           | `from tests.helpers import …` | not needed       | needs `extraPaths`, see the cost |
| `importlib`                         | **impossible by design**      | not needed       | clean                            |

The two pytest pages that appear to contradict each other are both right, about different modes:

- On `prepend`/`append`: _"It is highly recommended to arrange your test modules as packages by
  adding `__init__.py` files to your directories containing tests."_ So packaging tests is
  **pytest's own recommendation for the mode this repo uses**, not a workaround.
- On the `src` layout with tests outside the package: leaving `__init__.py` out _"should just work"_
  — which is true, and is what this repo does, at the cost of the basename rule.
- For new projects it recommends `importlib` outright, with `addopts = ["--import-mode=importlib"]`.

[PITFALL: `importlib` solves the basename problem and creates a worse one for the case that started
this. Its documented drawbacks are _"Test modules can't import each other"_ and _"Testing utility
modules in the tests directories (for example a `tests.helpers` module containing test-related
functions/classes) are **not importable**"_ — precisely the shared-helper use case a consumer
reached for. Its answer is to move helpers into the application package (`app.testing.helpers`),
which is a real design position but a different one from "put helpers in tests/".]

## What the community does, measured

14 well-known projects, checked 2026-08-30 via the GitHub API for `tests/__init__.py`, a `src/`
directory, and an `import-mode` setting in `pyproject.toml`:

| project      | src layout | `tests/__init__.py` | import mode   |
| ------------ | ---------- | ------------------- | ------------- |
| attrs        | yes        | yes                 | **importlib** |
| requests     | yes        | yes                 | default       |
| black        | yes        | yes                 | default       |
| poetry       | yes        | yes                 | default       |
| cryptography | yes        | yes                 | default       |
| flask        | yes        | no                  | default       |
| click        | yes        | no                  | default       |
| urllib3      | yes        | no                  | default       |
| httpx        | no         | yes                 | default       |
| pydantic     | no         | yes                 | default       |
| rich         | no         | yes                 | default       |
| fastapi      | no         | yes                 | default       |
| sqlalchemy   | no         | no                  | default       |

Two clear signals and one caution:

- **The default import mode is what everyone uses.** 13 of 14 leave it unset. `importlib` is
  pytest's recommendation for new projects and is nearly absent in practice — only attrs.
- **Packaged tests are the modest majority**: 9 of 13 overall, and 5 of 8 among the src-layout
  projects that match this repo's shape. So the retired plan's implicit premise — that an unpackaged
  `tests/` is the normal thing — was not right either; the field is genuinely split, leaning
  packaged.
- [UNVERIFIED: this is a convenience sample of well-known projects, chosen by recall rather than
  sampled from anything. It is enough to show that both layouts are mainstream and that `importlib`
  is not, and it is not enough to put a number on "most projects". Widen it before quoting a
  proportion anywhere.]

## What the other tools suffer

Measured against this repo, packaged layout (`__init__.py` in `tests/`, `tests/unit/`,
`tests/integration/`) plus `extraPaths: ["."]`:

| tool               | result                             |
| ------------------ | ---------------------------------- |
| pytest             | 520 unit pass; 35 integration pass |
| ruff check /format | clean, 90 files                    |
| basedpyright       | 0 errors, 0 warnings               |
| coverage           | 98%, unchanged                     |

So nothing "suffers" mechanically. The whole cost is the one thing `extraPaths` changes about **what
the type checker will no longer object to**:

[PITFALL: `extraPaths: ["."]` puts the repo root on basedpyright's search path for files under
`tests/`, which makes `from src.repo_tasks import version` resolve clean. It is a second import
route to the same code — `import src.repo_tasks.version` and `import repo_tasks.version` produce
different module objects with separate state at runtime — and `src` resolves as a PEP 420 namespace
package, so no `src/__init__.py` is needed for the hazard to exist. Causal, measured 2026-08-30: the
identical import is a `reportMissingImports` error with `extraPaths` removed and nothing else
changed.]

**That cost is closable, which the retired plan did not consider.** ruff's `TID` family is already
in the shipped `select` list, so the guard is config only, no new dependency and no new rule family:

```toml
[lint.flake8-tidy-imports.banned-api]
"src" = { msg = "import the installed package (repo_tasks), not src.repo_tasks" }
```

Measured 2026-08-30 — it fires exactly on the hole:
`TID251 'src' is banned: import the installed package (repo_tasks), not src.repo_tasks`. A different
tool then enforces what the type checker stopped seeing, which is the arrangement the retired plan
rejected as "more moving parts" without pricing it at one config block.

## Open questions

**Answered 2026-09-04** — whether the guard belongs in the shipped `ruff.toml` and whether it
generalises. It does ship, and it generalises by naming no package at all; in a flat-layout consumer
with no `src/` it is inert rather than wrong. See the decision below.

**The shared-helper question is answered — measured 2026-08-30, and the answer is "real, recurring,
and already served two different ways, neither of them packaging."**

Every personal repo with a `tests/` tree was surveyed for a non-test, non-conftest module under it.
Nine repos have tests; **two have the shared-helper need, and they solve it differently**:

| repo          | tests | how the shared world is expressed                                                               |
| ------------- | ----- | ----------------------------------------------------------------------------------------------- |
| `scaffoldapy` | 3     | `tests/support.py`, imported by four files across `tests/`, `tests/unit/`, `tests/integration/` |
| `ingesta`     | 16    | a 159-line `tests/conftest.py` of session-scoped fixtures                                       |
| the other 7   | 2–29  | no helper module at all                                                                         |

`repo-tasks` itself has none: the only `__init__.py` and the only non-test module under its `tests/`
belong to `tests/fixtures/sample-service`, a fixture _project_, not the test tree.

[DECISION: the use case is not "one consumer once" — but it is also not evidence for packaging. Of
the two repos that have it, the one that **raised** the question (`ingesta`) answered it with
conftest fixtures, which is pytest's own mechanism, needs no `__init__.py`, no `extraPaths` and no
ruff guard, and works identically under all three import modes. That is the cheapest answer
available and it is already in production in the repo the requirement came from.]

[PITFALL: **the conftest answer does not transfer to `scaffoldapy`, and assuming it did was this
plan's own error on 2026-08-30.** The first write-up of the survey proposed folding `support.py`
into `tests/conftest.py` as the cheap fix, from a reading of that module's imports rather than of
the module. Its docstring records the move as already rejected there, for two failure modes it marks
confirmed live: a tier-local `tests/integration/conftest.py` shadows `tests/conftest.py` for that
tier only, surfacing as a silent direction-dependent `ImportError`; and that repo has a **second**
`tests/conftest.py` under `template/`, which wins outright whenever pytest falls back to searching
from the working directory — precisely what the shipped `testpaths = tests/unit` triggers in a repo
that has not split its tests. So `from conftest import X` is ambiguous there in two independent
ways, and a distinct module name is the existing fix rather than the problem. The general lesson is
narrower than the specific one: a helper's _shape_ is a property of the repo it lives in, and two
repos solving "shared test world" differently is not evidence that either could adopt the other's
solution.]

[PITFALL: `scaffoldapy`'s route is the one with the latent problem, and it is exactly the basename
rule. `tests/conftest.py` does a bare `from support import BASE_ANSWERS, TEMPLATE_DIR, Render` —
which works only because `prepend` puts `tests/` at the **front** of `sys.path`, making a top-level
module named `support` shadow anything else by that name for the whole session. `support` is about
as collidable as a module name gets. So the repo that would benefit most from a packaged `tests/` is
the one already relying hardest on the property packaging would remove.]

[NEEDS CLARIFICATION: whichever way this goes, does `scaffoldapy` generate it? The layout reaches
new projects only through that template, and that repo's own
`plans/2026-08-30-generated-test-layout.md` already owns the generated `tests/` tree — it was filed
there from here on 2026-08-30, and explicitly waits on this plan before writing anything about
basenames into the generated `AGENTS.md`. Same coupling the retired plan had, now at least pointing
the right way round.]

## Recommended direction

On the user's own criterion — keep pytest's default and what the community actually uses — the
answer is **`prepend` (already the default, and unanimous in the sample) plus `__init__.py`**, which
is what pytest explicitly recommends for that mode and what the majority of comparable src-layout
projects do. `importlib` is the one option to rule out on that criterion: pytest recommends it for
new projects, but the field has not followed, and it forecloses shared test helpers permanently.

That means taking `extraPaths` after all, with the ruff `banned-api` guard alongside it so the
second import route is blocked rather than merely unwatched. The measurements above say that
combination costs nothing that any tool here can detect.

**That was written before the second open question was answered, and the answer weakens it.** The
survey above found the shared-helper need in two of nine repos, and in neither case is packaging
what serves it: `ingesta` uses conftest fixtures, `scaffoldapy` a bare top-level import. So the case
for `extraPaths` no longer rests on an unmet need — it rests on `scaffoldapy`'s
`from support import` being judged too fragile to leave alone, which is a narrower and more honest
reason than the one this plan started with.

Three coherent positions, and choosing between them is the remaining decision:

1. **Change nothing.** The false "standing requirement" claim is already corrected in
   `contributing/type-checking.md`, which was the only thing that had to happen. Both repos with the
   need are working. The basename rule stays, documented rather than implied.
2. **Package `tests/` family-wide** — `__init__.py`, `extraPaths: ["."]`, the ruff `banned-api`
   guard. Measured to cost nothing mechanically. Buys `scaffoldapy` a real `tests.support` import
   and removes the shadowing hazard; costs a second import route that only a lint rule closes.
3. **Fix `scaffoldapy` alone, by renaming the module.** `support.py` → a name nothing else would
   claim at the top of `sys.path` (`_scaffoldapy_test_support.py`). One `git mv` and three import
   lines, no family-wide config change, and it commits that repo to no layout. It does not remove
   the shadowing mechanism, only the realistic chance of a collision.

Option 3 first read "move it into conftest, the `ingesta` shape" — that is struck, per the pitfall
above: the move is already rejected in `scaffoldapy` on evidence.

## Decided: option 2, and landed in `repo-tasks`

[DECISION: **option 2 — package `tests/`, family-wide.** The user's call, 2026-09-04: "we want to
have pytest canonical. we want `__init__.py` in there. the fallout for basedpyright is weird, but if
ruff configuration shores that off, then it's fine." The deciding criterion is that this is pytest's
own documented shape for the `prepend` import mode this family uses, rather than a workaround — the
survey's community sample and the two-of-nine helper count informed the choice but did not make it.]

What landed here, 2026-09-04:

- `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`.
- `extraPaths: ["."]` in the shipped `pyrightconfig.json`, with the reasoning inline.
- `[lint.flake8-tidy-imports.banned-api]` banning `src` in the shipped `ruff.toml` — the guard that
  pays for it.
- `contributing/type-checking.md` "Why `tests/` is a package" and `contributing/test-tiers.md`
  "`tests/` is a package, so test module basenames need not be unique", both rewritten from the
  earlier not-permitted framing.

Both halves verified rather than assumed, 2026-09-04:

- **The guard fires.** `from src.repo_tasks import version` in a test drew
  `TID251 'src' is banned: import the installed package, not the src/ path to it — they are two
  different modules at runtime`.
- **The basename freedom is real, and was genuinely absent before.** Two `test_dupe.py` files, one
  per tier, collect and pass now; with the three `__init__.py` files removed and nothing else
  changed, the same two are a hard collection error
  (`which is not the same as the test file we want
  to collect ... use a unique basename`), exit 2.
- Full gate green throughout: 529 tests, basedpyright 0 errors 0 warnings, ruff clean.

[DECISION: the ban's message names no package, because the shipped `ruff.toml` goes to every
consumer byte-identical. In a flat-layout consumer such as `power-user-linux-setup`, with no `src/`
directory at all, the rule is **inert rather than wrong** — it can never trigger. That answers this
plan's first open question: the guard does ship, and it generalises by saying less.]

[DECISION: the `_integration` suffix on integration modules is **kept and not renamed**, though
packaging has made it descriptive rather than load-bearing. A rename would churn every integration
module to buy nothing, and the suffix still tells a reader which tier a file belongs to when it
shows up alone in a traceback.]

## What is left

[DEFERRED: **`scaffoldapy` still generates the unpackaged tree**, and the shipped configs now assume
the packaged one. That repo's own `plans/2026-08-30-generated-test-layout.md` was explicitly waiting
on this decision before writing anything about basenames into the generated `AGENTS.md`; the wait is
over and the answer is "packaged". Filed there rather than done here.]

[DEFERRED: **`scaffoldapy`'s `tests/support.py` can now become `tests.support`**, which is the fix
rather than the mitigation — its bare `from support import ...` currently resolves by `sys.path`
shadowing. Tracked in that repo's `2026-08-30-scaffoldapy-shared-test-helper.md`, whose recommended
rename is now superseded by this decision.]

[DEFERRED: **the other consumers pull the new configs on their own schedule.** `configs.pull` is
what delivers `extraPaths` and the ban; until a repo runs it, it keeps the old pair. A consumer that
pulls the configs but does not add `__init__.py` files is in a coherent state — `extraPaths` alone
was measured to cost nothing on an unpackaged tree — so there is no ordering hazard, only a window
where the family is mixed.]

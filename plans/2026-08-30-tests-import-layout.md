---
status: idea
updated: 2026-08-30
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

[NEEDS CLARIFICATION: does the guard belong in the shipped `ruff.toml`, and does it generalise? The
message names `repo_tasks`, and the ban is only meaningful in a repo whose package sits under
`src/`. A flat-layout consumer like `power-user-linux-setup` has no `src/` at all, so the entry is
inert there rather than wrong — but "inert in some consumers" is a property worth stating
deliberately, and the shipped configs otherwise avoid per-repo values. A generic message would fix
the naming half.]

[NEEDS CLARIFICATION: is the shared-helper use case real for this family, or was it one consumer
once? It is the entire reason any of this came up (`ingesta`, 2026-08-27, wanting a synthetic-world
helper imported across several unit modules). If the honest answer is that helpers belong in the
application package — which is `importlib`'s position and a defensible one — then the current
unpackaged layout is fine and only the false "standing requirement" claim needed correcting.]

[NEEDS CLARIFICATION: whichever way this goes, does `scaffoldapy` generate it? The layout reaches
new projects only through that template, and
[`2026-08-27-generated-test-layout.md`](2026-08-27-generated-test-layout.md) already owns the
generated `tests/` tree. Same coupling the retired plan had, unresolved for the same reason.]

## Recommended direction

On the user's own criterion — keep pytest's default and what the community actually uses — the
answer is **`prepend` (already the default, and unanimous in the sample) plus `__init__.py`**, which
is what pytest explicitly recommends for that mode and what the majority of comparable src-layout
projects do. `importlib` is the one option to rule out on that criterion: pytest recommends it for
new projects, but the field has not followed, and it forecloses shared test helpers permanently.

That means taking `extraPaths` after all, with the ruff `banned-api` guard alongside it so the
second import route is blocked rather than merely unwatched. The measurements above say that
combination costs nothing that any tool here can detect.

Do not treat this as settled: the second open question could reasonably kill the whole thing, and it
is the cheapest one to answer.

---
status: idea
updated: 2026-11-25
source_repo: github.com-personal/hekate
---

# An imports_check step in quality.check, for repos that declare import-linter contracts

## Context

hekate enforces its package layering with import-linter contracts in the root `pyproject.toml`'s
`[tool.importlinter]`. `quality.check` is a fixed tuple (`_CHECKS` in `repo_tasks/quality.py`) with
no way for a consumer to add a step, so hekate runs the contracts from a unit test
(`tests/unit/test_architecture.py`) that runs the `lint-imports` executable in a subprocess. That
works, but it hides an architecture check inside the test tier and every consumer wanting one would
re-write it.

[PITFALL: the test first called `importlinter.cli.lint_imports` in-process, and that silenced
logging for every test after it: import-linter configures logging with `logging.config.dictConfig`,
which disables every logger that already exists, so a later `caplog` assertion in hekate failed. Run
`lint-imports` as its own process, in the task too. Found in hekate 2026-11-26, its PR #28.]

## Recommended direction

- An `imports_check` task in `_CHECKS` that runs `lint-imports` when the repo declares contracts
  (`[tool.importlinter]` in `pyproject.toml`, or an `.importlinter` / `setup.cfg` section), and
  no-ops cleanly otherwise, the way `dockerfile_check` does for a repo with no Dockerfiles.
- `import-linter` in the canonical dev tool list, since it is pure Python, dev-only and small (2.17:
  a 652 kB wheel; deps click, grimp, rich).
- Once it ships, hekate drops its unit test in favour of the step.

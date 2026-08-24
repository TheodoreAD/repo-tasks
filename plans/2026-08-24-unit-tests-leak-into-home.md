---
status: idea
updated: 2026-08-24
---

## Context

`tests/unit/test_agents.py` calls `agents.wire_claude_hook` against `tmp_path` in four tests.
`agents.py` derives the env-cache directory from `Path.home()` (`_CLAUDE_ENV_CACHE_DIR`), so each
call also writes a `tmp-pytest-of-<user>-pytest-<n>-<test>-direnv-env` file into the developer's
real `~/.cache/claude-code/`. Measured 2026-08-24: ~366 such files on the dev machine, one per test
per run, every one pointing at a `pytest-of-*` directory that no longer exists.

This contradicts the unit tier's own contract — `tests/unit/conftest.py`: "no subprocesses, no
network, no Docker, nothing outside tmp_path" — and it is the same defect `scaffoldapy` fixed in its
e2e tier the same day (its `tests/integration/conftest.py`, autouse `isolated_home`). It is
invisible in `contributing/test-tiers.md`'s clean-OS reasoning because that tier only ever looked at
_integration_ tests as the ones that mutate `$HOME`.

## Open questions

- [NEEDS CLARIFICATION: fixture or code? An autouse `isolated_home` in `tests/unit/conftest.py`
  (fake `HOME` via `monkeypatch.setenv`; no plumbum concern here, nothing in this tier shells out)
  fixes every current and future test in one place and matches `tmp_cwd`'s "taking a fixture is
  something you can't forget" reasoning. Alternatively `agents.py` could resolve the cache dir
  lazily from an injectable base, which is a production change made for a test's convenience. The
  fixture is the smaller, tier-consistent fix; the question is whether `_CLAUDE_ENV_CACHE_DIR` being
  computed at import time is itself worth changing — it already forbids overriding `HOME` after the
  module is imported, which is exactly what a conftest fixture would try to do unless the constant
  becomes a function.]
- [NEEDS CLARIFICATION: should the unit-tier contract be enforced rather than documented — e.g. a
  session-scoped check that `~/.cache/claude-code` and `~/.local/share/direnv/allow` have the same
  entry count before and after the tier? Cheap, but it is a test about the test suite; the
  `plan-docs`/`~/AGENTS.md` stance is "teach what to run, not silently correct", which argues for
  the fixture plus the rule now in `~/AGENTS.md` ("Verifying behavior in a repo with test coverage")
  over a guard.]

## Recommended direction

Autouse `isolated_home` in `tests/unit/conftest.py`, plus making `agents.py` read `Path.home()` at
call time rather than at import so the override actually lands. Then purge the stale files once
(`find ~/.cache/claude-code -name 'tmp-pytest-of-*' -delete`) and note the fixture in
`contributing/test-tiers.md`'s unit-tier section, next to `tmp_cwd`.

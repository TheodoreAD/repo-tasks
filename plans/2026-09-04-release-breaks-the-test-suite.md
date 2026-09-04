---
status: landed
updated: 2026-09-04
---

# Bumping the version turns the test suite red

## Context

Found 2026-09-04 by cutting this repo's first real release. `inv trunkflow.cut --bump minor` did
exactly what it should — bumped `0.1.0` to `0.2.0`, rewrote `uv.lock` to match, committed and tagged
`v0.2.0` locally — and then **`inv quality.precommit` failed: 11 tests, 541 passing.**

The bump was undone (`git tag -d v0.2.0`, `git reset --hard` to the commit before it, by explicit
SHA), so the repo is back at `0.1.0` with a green gate and nothing was pushed. Nothing about the
release machinery is broken; this is a pre-existing property of the tests that only a real bump
could surface.

**This blocks releasing at all.** Not because the release fails, but because it lands a commit whose
gate is red — and the tag would point at it. A release commit that cannot pass the repo's own gate
is not a release.

## The cause

A number of unit tests assert against version strings **derived from this repo's own real
`pyproject.toml`**, not from a fixture. The test files say so themselves — `test_gitflow.py`'s
docstring explains that branch names "come from `version.next_version`'s pure arithmetic on this
repo's real pyproject.toml version (same fixture value `test_version.py` relies on)".

So `next_version("0.1.0", "minor")` is `0.2.0` and the tests hardcode `v0.2.0`; after a bump the
same call returns `0.3.0` and every such assertion fails. The value was stable only because the
version had never moved.

[PITFALL: this is invisible to every check that does not actually bump. The gate is green, the tests
are green, and the release tasks are unit-tested against `MockContext` — which is precisely what
cannot catch it, since the mock never runs `bump-my-version` and never rereads `pyproject.toml`. The
first real bump is the only thing that finds it, which is an argument for cutting a release early
rather than late.]

Measured: 11 failures across `test_version.py`, `test_gitflow.py` and `test_trunkflow.py`. Not every
literal `0.1.0` in the suite is affected — most are synthetic
`PythonProject(name="sample", version="0.1.0")` constructions, which are fixtures and stay correct.
The affected set is specifically the tests that resolve **the real project** and then assert a
literal.

## Open questions

**Answered 2026-09-04 by the user: (a).** A `pinned_version` fixture in `tests/unit/conftest.py`
replaces the resolved project's version with a fixture value, so the assertions stop depending on a
fact about this repo. Landed in `cd3d9ba`.

[DECISION: scoped to _this repo's own_ version rather than to every resolution, which the first
attempt got wrong. `set_dev`'s test writes a `pyproject.toml` into `tmp_cwd` and asserts against the
version it put there, so blanket-replacing whatever `_resolve_project` returned broke it. The
fixture reads the real version once at import and swaps only that value.]

[DECISION: autouse, not opt-in. The failure mode is a test _silently_ depending on the repo's
version, and an opt-in fixture only protects the tests someone remembered to opt in.]

Two tests are fixed rather than pinned, because the fixture cannot reach them and should not:
`test_discover_python_projects_returns_repo_root_first` calls discovery directly and now asserts
identity, which is what its name describes; `test_bump_...returns_new_version` reads through
`discover_python_projects` and now asserts that the return value reports what the file says, which
is what it always meant.

Verified the way the bug was found rather than by reasoning: set the version to `0.9.0`, run the
suite, revert. 552 pass at both values. `v0.2.0` was then cut, gated green, and pushed.

**Should something stop this recurring?** Not decided here, and moved out rather than dropped: the
class of bug is "a test asserts a literal derived from mutable repo state", and the version is
unlikely to be the only such value. Now owned by
[`2026-09-04-tests-asserting-mutable-repo-state.md`](2026-09-04-tests-asserting-mutable-repo-state.md).

## Recommended direction

Fix before releasing anything — the release cannot be clean until the gate is green on the bump
commit. (a) with a shared fixture is the smallest change that makes the affected tests independent
of the repo's own version, and it is worth doing as its own commit, verified by bumping, running the
gate, and resetting again exactly as this plan's discovery did.

Then re-cut `v0.2.0`. It is still a minor under the surface rule: shipped configs, the
`repo-tasks-quality` manifest and the reusable workflow have all moved since `0.1.0`.

**Done.** `cd3d9ba` landed the fixture, `cef6894` was the bump, and `v0.2.0` was cut, gated green
and pushed 2026-09-04.

## Migrated to

- [`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Unit tier: mocked `c.run`" —
  the pitfall, as a second paragraph beside the blind spot it is an instance of. It belongs there
  rather than under versioning or the release flow because nothing about the release machinery was
  wrong: what failed is a property of how the tests were written, and the reason it survived to a
  release is that a `MockContext` cannot run `bump-my-version`.
- `tests/unit/conftest.py` — both decisions were already there before this retirement, in
  `pinned_version`'s docstring: why it is autouse (the failure mode is a _silent_ dependence, so
  opt-in protects only the tests someone remembered) and why it is scoped to this repo's own version
  (blanket-replacing every resolution broke `set_dev`'s test, which writes its own `pyproject.toml`
  and asserts against it). Its pointer here was repointed at `contributing/test-tiers.md`.
- [`2026-09-04-tests-asserting-mutable-repo-state.md`](2026-09-04-tests-asserting-mutable-repo-state.md)
  — the deferred general question, as its own plan, with the three values that share the shape and
  the reason the class matters at all: a test that fails only when the repo changes normally gets
  edited to match rather than questioned.

**Deliberately not migrated.** The failure count, the list of affected test files, and the
set-to-`0.9.0`-and-revert verification are dropped: they describe a state that no longer exists, and
the fixture plus its test are now the standing assertion that it does not recur.

---
status: idea
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

[NEEDS CLARIFICATION: which fix? (a) a fixture that stubs the resolved project's version to a fixed
synthetic value, so every affected test asserts against a version the repo will never actually have
— the version becomes test data rather than a fact about the repo; (b) compute the expected value in
the test from `next_version(current_version(...))`, which keeps the tests self-consistent but makes
them tautological, asserting the function against itself; (c) point the affected tests at a fixture
`pyproject.toml` under `tests/fixtures/` with a pinned version, which is (a) with the stub living in
a file. (a) or (c) look right and (b) does not, since the arithmetic is exactly what those tests
exist to pin.]

[NEEDS CLARIFICATION: should something stop this recurring? The class of bug is "a test asserts a
literal derived from mutable repo state", and the version is unlikely to be the only such value —
the repo name, the Python floor and the dependency-group contents have the same shape. A test that
fails only when the repo changes in a normal way is a test that will be edited to match rather than
questioned, which is how the assertion quietly stops meaning anything.]

## Recommended direction

Fix before releasing anything — the release cannot be clean until the gate is green on the bump
commit. (a) with a shared fixture is the smallest change that makes the affected tests independent
of the repo's own version, and it is worth doing as its own commit, verified by bumping, running the
gate, and resetting again exactly as this plan's discovery did.

Then re-cut `v0.2.0`. It is still a minor under the surface rule: shipped configs, the
`repo-tasks-quality` manifest and the reusable workflow have all moved since `0.1.0`.

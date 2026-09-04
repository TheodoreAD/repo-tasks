---
status: landed
updated: 2026-09-05
---

# Tests that assert a literal derived from mutable repo state

## Context

Carried out of the now-retired `plans/2026-09-04-release-breaks-the-test-suite.md`, which fixed one
instance of this and deliberately did not decide the general question.

The instance: 11 unit tests asserted version strings derived from this repo's real `pyproject.toml`
— a branch named `release/0.2.0`, a `--new-version` argument, a tag that must not already exist.
They were correct only while the version never moved. Cutting the first real release moved it and
they went red, on the commit a release tag would have pointed at. The fix is an autouse
`pinned_version` fixture in `tests/unit/conftest.py`; the confirmed pitfall about why nothing caught
it earlier is in [`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Unit tier:
mocked `c.run`".

**The class is wider than the version, which is why this is worth its own file.** The same shape is
available to any test that resolves the real project and then asserts a literal about it, and this
repo has at least three other values with exactly that character: the repo's own name, the Python
floor in `requires-python`, and the contents of the dependency groups. None of those is asserted
literally today as far as the version case's fix had to look — but nothing stops the next test from
doing it, and the failure arrives at the worst possible moment, since each of those values changes
precisely when someone is doing something deliberate and wants a green gate to confirm it.

What makes it worth more than a shrug is the second-order effect: **a test that fails only when the
repo changes in a normal way is a test that gets edited to match rather than questioned.** The
literal is updated, the suite goes green, and the assertion quietly stops meaning anything — it now
asserts that two copies of the same fact agree, which they will, forever.

## Resolved 2026-09-05

The three questions this plan carried, each answered by the recommended direction it already had:

- **Anything beyond the fixture?** No. One observed instance is not a class, and a mechanism built
  against three hypothesised values is the speculative-need shape `~/AGENTS.md` warns about. The
  fixture stays the whole answer; the next instance, if there is one, argues for more with evidence.
- **Test or convention?** Convention. A detector would have to know where an expected value came
  from, a data-flow question a test cannot ask about itself, so the rule is stated in
  `contributing/test-tiers.md` and enforced by review. `pinned_version` grows to cover the next
  real-project value when a test first reaches for it, not in advance.
- **Does the exposure exist in what `scaffoldapy` generates?** In principle yes — a generated repo
  inherits the convention, not the conftest, and its version moves on the same release path. That is
  that repo's question, filed for it as
  `plans/2026-09-05-tests-asserting-literals-from-generated-repo-state.md` in its store mirror.

## Migrated to

- [`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Unit tier: mocked `c.run`" —
  the decision, as a `[DECISION:]` tag directly under the pitfall that motivated it.
- The `scaffoldapy` half, as the plan named above.

Deliberately not migrated: the second-order argument about a test that gets edited to match rather
than questioned. It is the reasoning behind the decision, not a rule of its own, and the decision
tag states the rule.

---
status: idea
updated: 2026-09-04
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

## Open questions

[NEEDS CLARIFICATION: is there anything to do beyond the one fixture, or is the honest answer "this
was one bug, it is fixed, stop"? The case for stopping is real: three hypothesised values is not
three observed bugs, and building a mechanism against a class nobody has been bitten by twice is the
speculative-need shape `~/AGENTS.md` warns about. The case against is that the one instance was
invisible until a release, and the other three values are each harder to move than the version, so
their instances would sit undiscovered for longer rather than not existing.]

[NEEDS CLARIFICATION: if something is worth doing, is it a test or a convention? A test would have
to detect "this assertion's expected value came from the repo's own state", which is a data-flow
question a test cannot easily ask about itself. A convention — resolve-the-real-project values are
pinned by a fixture, never asserted literally — is enforceable only by review, which in this repo
means by whoever is reading. That asymmetry probably decides it, but it has not been thought
through.]

[NEEDS CLARIFICATION: does the same exposure exist in what `scaffoldapy` generates? A generated repo
inherits this repo's test conventions but not its conftest, and its own version moves on the same
release path. If the answer to the question above is a convention, the generated `AGENTS.md` is
where it would have to be said, which makes this a cross-repo question rather than a local one.]

## Recommended direction

Rough, and deliberately behind the questions above.

The cheapest honest thing is to leave the fixture as the whole answer and let the next instance,
should there be one, argue for a mechanism with evidence rather than with a hypothesis. That is not
the same as doing nothing: the pitfall is written into `contributing/test-tiers.md`, so the next
person to hit it finds an explanation instead of rediscovering the cause.

If it does turn out to want more, the shape most likely to pay for itself is the narrow one —
extending `pinned_version` to cover whichever other real-project value a test first reaches for,
rather than a general rule about literals. The fixture already demonstrates the tricky part, which
is being scoped to _this_ repo's value so a test that builds its own project on disk keeps the value
it chose.

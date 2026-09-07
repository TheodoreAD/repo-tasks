---
status: landed
updated: 2026-09-08
---

# test_cut_bumps_and_tags_straight_to_a_final_version is flaky on a temp filename

## Context

Found incidentally on 2026-09-05 while running the gate for an unrelated change. One run in roughly
twenty fails:

```
    def test_cut_bumps_and_tags_straight_to_a_final_version():
        c = _ctx()
        trunkflow.cut.body(c)
        calls = [call[0][0] for call in c.run.call_args_list]
        bump = next(cmd for cmd in calls if cmd.startswith("bump-my-version"))
        assert bump.startswith("bump-my-version bump minor --config-file ")
>       assert "rc" not in bump
E       AssertionError: assert 'rc' not in 'bump-my-ver...ersion 0.2.0'
E         'rc' is contained here:
E           p/tmpe8ifurcm.toml --new-version 0.2.0
```

The assertion means "this bump produced a final version, not a release candidate", and it checks for
`rc` in the **whole command string** — which also contains the path of a `mkstemp`-generated config
file. `tempfile` builds those names from a random 8-character alphabet, so any name containing the
adjacent letters `r` and `c` fails the test. Here it was `tmpe8ifurcm.toml`.

Nothing to do with the version logic, which is correct in every run. The subject under test appears
twice in the string and only one occurrence is meant.

Roughly a 1-in-20 failure — high enough to have hit twice in one session, low enough that it reads
as a fluke rather than a bug, which is the worst rate for something a red CI run gets blamed on.

[PITFALL: that rate was estimated from having hit it twice, and it is about ten times too high.
Measured 2026-09-08 over 200,000 generated candidate names: **1 in 198**, which is also what the
arithmetic says — seven adjacent pairs in an eight-character name over `tempfile`'s 37-character
alphabet is 7/37², or 1 in 195. Two hits in one session was luck, not the rate. The correction makes
the argument stronger rather than weaker: at 1 in 200 nobody ever sees it twice close enough
together to suspect a pattern, so it is attributed to whatever else changed that day.]

## Recommended direction

Assert against the part of the command the test is actually about, not the whole line. The
`--new-version` value is the subject:

```python
assert bump.endswith("--new-version 0.2.0")
```

or parse the flag's value out and assert `"rc" not in` that alone. Either way the temp path stops
being in scope.

[DECISION: do not "fix" it by making the temp filename deterministic. The randomness is `tempfile`'s
job and is right; the test's reach is what is wrong, and narrowing the assertion fixes the class
rather than this instance.]

Worth a grep for siblings while in there — any other assertion of the form
`assert "<short string>" not in <whole command>` where the command embeds a generated path has the
same defect. `trunkflow.py` and `release.py` both build commands around a temp config file.

## Open questions

[DECISION: checked 2026-09-08, and there is no sibling — in `test_release.py` or anywhere else in
the suite. Every other substring-absence assertion either reads a haystack with no generated path in
it, or searches for something long enough that a random name cannot produce it: `--new-version`,
`--cov-fail-under`, `dependency-groups.dev`. `rc` was the only needle short enough to collide, which
is the property worth carrying forward rather than the file it happened to be in — a two-character
needle against a string holding a generated path is the shape to refuse at review.]

## Verification (2026-09-08)

Fixed as recommended: the assertion now reads the flag rather than the line.

```python
assert bump.endswith("--new-version 0.2.0")
```

That asserts more than the old one did, not less — it pins which final version the bump lands on,
where `"rc" not in bump` only pinned that it was not a candidate. The temp path is out of scope
entirely, so the failure class is gone by construction rather than made rarer.

The new assertion is load-bearing without any source change to prove it, because both sides of the
contract are already covered: `test_bump_maps_parts_onto_bumpversion_components` asserts
`--new-version` is **absent** on the rc path, and
`test_bump_states_the_final_version_outright_when_rc_is_off` asserts it is present on the final one.
Dropping the flag would fail those first.

Gate green, 635 tests. Pushed in `16df75c`; CI green on that push.

## Migrated to

[`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Unit tier: mocked `c.run`" —
which already held the sibling finding about unit tests asserting mutable repo state, so the two sit
together as one concern rather than as two anecdotes. Both are the same defect seen twice: an
assertion that reached past its own subject.

- The decision, plus the sweep result that no sibling exists and the reusable shape (a short literal
  searched for in a string embedding a generated path).
- The rate correction, as a pitfall about estimating flake rates from the clusters you happen to
  notice.

Deliberately not migrated: the failure transcript and the before/after assertion, which are in
`571387f` and in the test file itself; and the note that `trunkflow.py` and `release.py` both build
commands around a temp config file, which was a pointer for the sweep that has now been done.

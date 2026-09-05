---
status: idea
updated: 2026-09-05
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

[NEEDS CLARIFICATION: whether the same shape exists in `test_release.py`. Not checked — this was
found mid-way through unrelated work and written down rather than chased.]

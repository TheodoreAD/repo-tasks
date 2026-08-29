---
status: done
updated: 2026-08-29
---

# The integration tier is red on `main`

## Context

Found incidentally on 2026-08-26 while verifying that `pytest.ini`'s new `filterwarnings = error`
did not break anything: the integration tier was **already failing before that change**, and had
been. Established against a stashed baseline rather than assumed — `main` at `b11355e` gives
`1 failed, 19 passed, 7 errors`, identical with and without the pytest change.

Every one of the eight is the same cause:

```
ValueError: unsupported version 'test' — expected X.Y.Z, X.Y.ZrcN, or a dev build
X.Y.Z[rcN].devN[+gHASH]
src/repo_tasks/version.py:60: ValueError
```

Two fixtures monkeypatch `current_version` to the literal string `"test"`:

- `tests/integration/conftest.py`'s `clean_os_container`
  (`mp.setattr(docker_tasks,
  "current_version", lambda c, group=None: "test")`) — takes down all
  three of `test_clean_os_integration.py` and all four of `test_clean_os_user_effects.py` at fixture
  setup.
- `tests/integration/test_docker_integration.py`'s `test_build_and_push_round_trip`, the same way.

`version.py` now validates the string it is handed, and `"test"` is not a version. The fixtures
predate that validation.

Not caused by this session's work, and deliberately not fixed in it — the session was landing
quality-gate changes, and quietly repairing an unrelated red tier inside that work would have hidden
it. It is written down here instead so it is not rediscovered a third time.

## Open questions

~~Is the fix the fixtures or the validation?~~ Resolved 2026-08-29: the fixtures, as recommended
below. Two details this question got wrong, both found by making the change:

- `"0.0.0.dev0+gtest"` is **not** a shape `version.py` accepts — `_PEP440`'s commit group is
  `[0-9a-f]+` and `test` is not hex. A dev build needs a real hex stand-in (`+gdeadbee`).
- The two fixtures cannot take the same value. `clean_os_container` starts its container from
  `:latest`, and `docker.release` deliberately skips the `latest` tag for a pre-release, so a dev
  build there produces an image that is never tagged and a fixture that fails one step later. It
  takes the final `"0.0.0"`; only `test_build_and_push_round_trip`, which calls `build`/`push`
  directly, takes the dev build — and there it earns its keep, since asserting the pushed tag is
  `0.0.0-dev.0.gdeadbee` is what proves the PEP 440 `+` local segment never reaches a registry.

[NEEDS CLARIFICATION: when did this start failing, and why did nothing catch it? The tier is opt-in
and runs on nobody's commit — `contributing/test-tiers.md` says so deliberately — so "no gate covers
it" is the designed behaviour, not an oversight. The question is whether an opt-in tier that can sit
broken indefinitely is worth a periodic run, which overlaps with the scheduled-run question deferred
in [`2026-08-26-quality-tool-gaps.md`](2026-08-26-quality-tool-gaps.md) §1.]

~~Whether the tier passes once the version strings are valid.~~ Answered 2026-08-29, and the answer
was no — there was a second cause behind the fixture, exactly as this tag suspected. See "What was
behind it" below. Re-measured 2026-08-28 on `863ede6` against a real daemon (Docker 29.7.2):
`1 failed, 24 passed, 7 errors` in 22s, all eight red the same `ValueError`, no second cause
_visible_ — which is the point: the one that existed could not show itself while the fixture errored
at setup.

## Recommended direction

Change the fixtures, not the validation — a fixture asserting on an invalid version is the thing
that is wrong, and `version.py`'s validation is load-bearing for the release flow. Then run the
whole tier and see what is behind it.

## What was behind it (2026-08-29)

With both fixtures on valid versions, all 32 tests pass — and the run still exits 1, from
`pytest_unconfigure`, after the last test has already gone green:

```
ExceptionGroup: multiple unraisable exception warnings (42 sub-exceptions)
  ResourceWarning: unclosed file <_io.FileIO name=50 mode='rb' closefd=True>
```

`invoke`'s `Local` runner never closes the subprocess pipes it opens. Every real `c.run` leaks two
or three file objects, and `filterwarnings = error` promotes each one the collector reaches into an
error that pytest's unraisable-exception plugin re-raises. Attributed with no test code involved at
all — `Context().run("true", hide=True)` then `gc.collect()` under `-W error::ResourceWarning`
reproduces it on invoke 3.0.3 — and confirmed by module: every integration module that drives a real
task is affected (6 to 30 warnings each), and `test_written_files_integration.py`, the one that
never shells out, is clean at exit 0.

This corrects a claim in `pytest.ini` itself. `filterwarnings = error` was "adopted while the
baseline was genuinely zero across both tiers"; it was zero across the _unit_ tier, and the
integration tier's cost was invisible because that tier was already red for the reason this plan is
about. The tier being opt-in is what let one failure hide the other.

The fix follows `pytest.ini`'s own written rule for where an ignore goes — that file, family-wide,
since every consumer's integration tier drives real tasks through `c.run`:

```
ignore:unclosed file:ResourceWarning
```

Narrowest filter that works; `-p no:unraisableexception` would have disabled the detection wholesale
instead. The accepted cost is that a genuine unclosed file in a consumer's own code is silenced with
invoke's — bounded, in that the only tier this reaches is the opt-in one.

### Verified

`inv test.integration` on this change: **32 passed in 42.02s, exit 0**. First green integration tier
recorded in this plan's history.

### What this leaves open

Only the second question above, unchanged: an opt-in tier that nobody's commit runs can sit broken
indefinitely, and whether it earns a periodic run is the scheduled-run trade-off deferred in
[`2026-08-26-quality-tool-gaps.md`](2026-08-26-quality-tool-gaps.md) §1. It belongs there, not here.

[DEFERRED: drop the `ResourceWarning` ignore once invoke closes its pipes. Nothing tracks invoke
releases for this, so it will be noticed whenever someone next reads `pytest.ini` — cheap to leave,
and the comment there names the condition.]

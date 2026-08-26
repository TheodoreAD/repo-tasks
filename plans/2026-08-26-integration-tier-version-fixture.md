---
status: idea
updated: 2026-08-26
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

[NEEDS CLARIFICATION: is the fix the fixtures or the validation? The fixtures want "some tag that is
not a real release" and `"test"` reads well in an image tag; `version.py` wants every version string
it handles to be parseable. A real version (`"0.0.0"`, or a dev build like `"0.0.0.dev0+gtest"`)
makes the fixtures honest without weakening validation, and the dev-build form is already a shape
`version.py` accepts.]

[NEEDS CLARIFICATION: when did this start failing, and why did nothing catch it? The tier is opt-in
and runs on nobody's commit — `contributing/test-tiers.md` says so deliberately — so "no gate covers
it" is the designed behaviour, not an oversight. The question is whether an opt-in tier that can sit
broken indefinitely is worth a periodic run, which overlaps with the scheduled-run question deferred
in [`2026-08-26-quality-tool-gaps.md`](2026-08-26-quality-tool-gaps.md) §1.]

[UNVERIFIED: whether the tier passes once the version strings are valid. Only the failure's single
common cause was established; nothing confirms there is not a second failure behind it.]

## Recommended direction

Change the fixtures, not the validation — a fixture asserting on an invalid version is the thing
that is wrong, and `version.py`'s validation is load-bearing for the release flow. Then run the
whole tier and see what is behind it.

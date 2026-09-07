---
status: in-progress
updated: 2026-09-08
source_repo: github.com-personal/scaffoldapy
source_session: 7a3f34e6-b0c7-4532-8c89-ec43239414e7.jsonl
source_moment: 2026-09-07T20:45:00Z
---

# Every web-service consumer's gate is red today, on a warning nobody in the family emitted

## Context

The shipped `pytest.ini`'s `filterwarnings = error` turns an import-time `DeprecationWarning` inside
`starlette.testclient` into a collection error, so a repo whose tests touch `fastapi.testclient`
cannot run `pytest` at all — `collected 0 items / 1 error`, `inv quality.check` exit 2, with no test
of its own having run.

```
starlette/testclient.py:53: in <module>
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]
anyio/_lazyimport.py:35: emit_deprecation_warning(module_name, name, new_name)
E   DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated,
    use anyio.from_thread.BlockingPortal instead.
```

Both halves are at their latest release, checked against PyPI 2026-09-07: **starlette 1.6.0** and
**anyio 4.15.1**. There is no version pair a consumer can resolve to today that avoids it, and
nothing a consumer writes in its own test file changes it — the warning fires while starlette's
module body is being executed, before any consumer code runs.

**It is already fixed upstream and unreleased.** starlette `main` (`f03f65c`, cloned into
`$RESEARCH_HOME` 2026-09-07) imports `anyio.from_thread` and annotates
`anyio.from_thread.BlockingPortal` at that same line 53. So the whole exposure is the window between
anyio 4.15.0 deprecating the alias and starlette's next release taking the rename.

This file already says where the answer goes, which is why the plan is filed here rather than in the
repo that found it:

> An ignore, when one is eventually needed, belongs right here: this file ships to every consumer
> via `configs.pull`, and the dependencies behind these warnings are the same everywhere, so a
> warning worth silencing is almost certainly worth silencing family-wide.

## Evidence

Found in `scaffoldapy`, session `7a3f34e6-b0c7-4532-8c89-ec43239414e7.jsonl` under
`~/.claude/projects/-home-tdumitrescu-projects-github-com-personal-scaffoldapy/`, 2026-09-07, while
running `inv test.all` to verify an unrelated GitHub Actions bump. The distinctive phrase to search
that transcript for is "the anyio.abc.BlockingPortal alias is deprecated".

**The repro needs no generation run**, in any repo whose tests import `fastapi.testclient` under the
shipped `pytest.ini`:

```shell
pytest            # collected 0 items / 1 error, ERROR collecting tests/unit/test_app.py
```

In `scaffoldapy` it is one parametrized case of the end-to-end tier —
`test_generated_repo_passes_quality_check_out_of_the_box[web_service-no-fetch]`, 9 of 10
combinations green — which renders a repo for real and asserts its own `inv quality.check` exits 0.
That test is the family's only check that a generated repo works out of the box, so this is what it
was built to catch.

The failure is attributable to nothing in that repo: it renders from a template whose last
web-service change (`ac4f170`, 2026-08-27) fixed the **previous** warning at the same import site by
adding `httpx2` to the generated dev group, on starlette's own recommendation. That fix still holds;
this is a second, independent deprecation reaching the same line.

## Open questions

[DECISION: an `ignore` entry, not waiting for starlette's release. The two entries this file already
carried are permanent conditions — pytest's own `testpaths` fallback, and invoke leaking pipe
handles — and this is the first one meant to be deleted. It went in anyway because the alternative
prices a red gate for every web-service consumer against a release date that is not ours to pick.
Re-checked on PyPI 2026-09-08: still starlette 1.6.0, so the window is open and not closing on its
own.]

[DECISION: matched on the message, not on the class. `ignore::DeprecationWarning` would silence the
category this file's `error` policy exists to surface; the message match keeps every other
deprecation loud and stops matching anything by itself the moment starlette ships the rename, which
is what makes it safe to forget. Both halves were measured rather than reasoned about — see
Verification.]

[NEEDS CLARIFICATION: is a temporary entry supposed to leave a trigger behind? The comment can say
"drop this once starlette releases the `anyio.from_thread` rename", the same shape as the invoke
`ResourceWarning` entry's "drop this once invoke closes them" — which is honest but is also a
sentence nothing ever re-reads. Whether that is good enough here, or whether an expiring ignore
wants something that actually notices, is the general question this is the first instance of.]

## Recommended direction

Add the message-matched `ignore` with a comment naming the upstream fix (`f03f65c` on starlette
`main`) and the condition for removing it, then let `configs.pull` carry it. It is the same
judgement the `unclosed file` entry already made — a third-party defect the family cannot fix and
should not be blocked by — with the difference that this one has an upstream fix already written.

Note the ordering for whoever takes it: `scaffoldapy`'s end-to-end tier renders against the
**globally installed** `repo-tasks`, not a checkout, so the verification there needs this pushed and
`inv repo-tasks.update` run in that repo before its `web_service` combination can go green.

## Verification (2026-09-08)

The entry landed in `487c9c8`, written into the root `pytest.ini` and promoted into the shipped copy
with `inv configs.promote --file pytest.ini --apply` — the direction this repo owns, rather than
editing the packaged file directly.

Measured against a throwaway project holding nothing but the shipped `pytest.ini` and one
`from fastapi.testclient import TestClient`, resolved with no project environment in the way, on the
current release of both halves:

| config                        | result                                            |
| ----------------------------- | ------------------------------------------------- |
| the file as it stood at HEAD  | `collected 0 items / 1 error`, exit 2, at line 53 |
| with the new entry            | `1 passed`                                        |
| plus an unrelated deprecation | that test **fails** — the narrow match holds      |

[PITFALL: the obvious probe does not reach this warning. Without `httpx2` installed, starlette's
testclient raises its own earlier deprecation at line 36 and collection dies there instead — a
different error at a different line, which reads as the bug reproducing when it is not. The `httpx2`
dependency that a real web-service consumer already carries is what exposes line 53, so a probe
built to be minimal is a probe that measures the wrong thing.]

The third check is the one that matters and is why the entry is spelled the way it is: silencing the
class would have passed the first two identically.

[UNVERIFIED: the original repro, in the repo that found it. This plan carries `source_repo`, so it
is not done until `scaffoldapy`'s `web_service` end-to-end combination goes green — and that needs
this pushed and `inv repo-tasks.update` run there first, per the ordering note above. Held
deliberately: the push is the user's call and was declined for now.]

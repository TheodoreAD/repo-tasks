---
status: idea
updated: 2026-08-30
---

# Which pytest plugins should the family standardise on?

## Context

`repo-tasks-quality` now ships two pytest plugins — `pytest-cov` and `pytest-socket` — and the
reasoning that put the second one there was never a survey. Each arrived from a specific section of
the quality-gate coverage sweep (now retired; its settled half is
[`../contributing/quality-gate.md`](../contributing/quality-gate.md)), answering one concern at a
time. The complementary question has not been asked, exactly as that sweep's own framing had it for
gate tooling: **which pytest plugins is the family missing entirely, and which of the well-known
ones has it deliberately not taken?**

Raised by the user 2026-08-27, alongside the decision to standardise the first two: "we should also
look for other very common pytest plugins to include ... I forgot to do this."

**The survey ran 2026-08-30.** Its results are below and its conclusion is narrow: the family is
missing almost nothing, and the one genuine gap is `pytest-timeout`.

### The selection criterion the first two established

Both `pytest-cov` and `pytest-socket` are **inert until something asks for them** — `--cov`,
`disable_socket()`. That is what made shipping them to every consumer, including ones that use
neither, cost nothing. It is also the sharpest available test for any candidate, and it disqualifies
a whole class of otherwise-popular plugins outright:

- A plugin that **changes behaviour on install** (reordering tests, rerunning failures) is not
  inert. It would alter every consumer's suite the moment `configs.ensure-deps` ran, with no opt-in.
- A plugin that **changes output on install** (progress bars, diff prettifiers) is not inert either,
  and this family's gate output is read by agents as well as humans.
- A plugin that **needs network, a daemon, or a service** cannot be in a manifest whose whole point
  is that `quality.check` runs offline in any consumer.

Weight is the weaker constraint, not the strong one: `pytest-socket` is an 8.7 KB pure-python wheel,
and `hadolint-py`'s 12 MB was accepted on its merits. Judge it, but do not lead with it.

## How the survey was run

Inertness was **measured, not reasoned**: this repo's own unit tier (528 tests) was run once as a
baseline and once per candidate with nothing changed but `uv run --with <candidate>`, and the two
outputs compared after normalising away ANSI escapes, uv's own resolver chatter, the `plugins:`
banner and every duration. A candidate is inert when that diff is empty.

[PITFALL: **the inertness run must go through a pty, or the measurement is wrong in the exact
direction that matters.** Piped to a file, `pytest-sugar` produced output byte-identical to the
baseline and was scored inert; the same run under `script -qec` replaced the reporter wholesale —
193 KB of progress bar and per-test checkmarks against the baseline's 7.5 KB. Output plugins check
for a terminal, so the cheap way to run the experiment is precisely the way that cannot detect them.
Both measurements were taken 2026-08-30; the piped one was believed first.]

[UNVERIFIED: `uv run --with` resolved CPython 3.14.5, while the repo's own gate runs the pinned
3.11.15. Every candidate passed 528/528 on both, so nothing here rests on the difference, but an
adoption decision that turns on version-specific behaviour should be re-measured on the floor.]

## Inertness, measured

Twenty-four candidates, all of them 528/528 passing with the plugin merely installed — **no
candidate broke this repo's `--strict-config`, `--strict-markers` or `filterwarnings = error`
settings**, which was the failure most likely to disqualify one cheaply.

| verdict                           | candidates                                                                                                                                                                                                                                                                                                                               |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **inert** (empty diff)            | `pytest-timeout`, `hypothesis`, `syrupy`, `pytest-httpx`, `respx`, `time-machine`, `pytest-freezer`, `pytest-rerunfailures`, `pytest-xdist`, `pytest-datadir`, `pytest-regressions`, `pytest-mock`, `pyfakefs`, `pytest-env`, `pytest-subprocess`, `pytest-recording`, `pytest-check`, `pytest-order`, `pytest-repeat`, `pytest-testmon` |
| **banner only** (one header line) | `pytest-asyncio`, `pytest-benchmark`                                                                                                                                                                                                                                                                                                     |
| **not inert**                     | `pytest-randomly` (47 lines — reorders every run), `pytest-sugar` (30 lines — replaces the reporter)                                                                                                                                                                                                                                     |

[DECISION: the inert/not-inert line falls in a different place than this plan assumed. It predicted
`pytest-randomly` as "the archetypal _not_ inert plugin" and that is exactly right — but it grouped
rerunning and reordering plugins with it, and **`pytest-rerunfailures`, `pytest-xdist`,
`pytest-order`, `pytest-repeat` and `pytest-testmon` are all measurably inert**: each does nothing
without its flag or marker. So the criterion acquits most of the class it was expected to convict,
and the rejections below have to stand on the concern, not on the mechanics.]

The two "banner only" cases add a single configuration header line and change no behaviour:
`asyncio: mode=Mode.STRICT, ...` and `benchmark: 5.3.0 (defaults: ...)`. That is a weaker violation
than a progress bar, and neither is being adopted for other reasons.

## The concern sweep: what is actually uncovered

Per the plan's own step 1 — sweep for concerns with no plugin behind them, rather than filtering a
popularity list. The concerns this family's test tiers actually have, and what answers each today:

| concern                                 | answered by                                         | gap?                         |
| --------------------------------------- | --------------------------------------------------- | ---------------------------- |
| line coverage                           | `pytest-cov` (shipped)                              | no                           |
| no network in the unit tier             | `pytest-socket` (shipped) + `no_network` autouse    | no                           |
| nothing written to the real `$HOME`     | `isolated_home` autouse fixture                     | no — and no plugin does this |
| nothing written outside `tmp_path`      | `tmp_cwd` fixture                                   | no                           |
| asserting the command a task builds     | invoke's own `MockContext` (14 unit modules use it) | no                           |
| async test collection                   | `anyio`, already present and configured             | no                           |
| **a hung test in the integration tier** | nothing                                             | **yes**                      |

[DECISION: **the honest answer to "which plugins is the family missing entirely" is: one.** The
concerns that looked plugin-shaped turn out to be answered by three autouse fixtures in
`tests/unit/conftest.py` and by a class invoke itself ships, and those answers are better than a
plugin would be — they are opt-in per tier rather than imposed through a config every consumer
inherits, which is the reasoning that conftest already states for the socket guard. The two
`$HOME`/cwd fixtures in particular cover a hazard `~/AGENTS.md` documents as recurring and for which
no maintained plugin exists at all.]

## Per-candidate verdicts

PyPI metadata read from each project's own JSON, 2026-08-30 — never from a search summary, per
`~/AGENTS.md`. "KB" is the largest wheel for the current release.

### Adopt into the manifest — landed 2026-08-30

| candidate        | version / date    | KB   | why                                                                                                                                                                                        |
| ---------------- | ----------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `pytest-timeout` | 2.4.0, 2025-05-05 | 14.0 | The one uncovered concern. Inert (no `--timeout`, no `timeout` ini key, no marker → does nothing). 24 releases since 2012: mature, not abandoned — the shape of a plugin that is finished. |

The integration tier drives real subprocesses, Docker and a package index; a hang there currently
ends as a CI job killed at `timeout-minutes` with no indication which test stopped, which is the
failure a per-test timeout turns into a named one.

### Recommend in `contributing/test-tiers.md`, do not ship

Each is inert and would cost nothing in the manifest, but covers a concern only some repos have — so
it lands as a named recommendation a repo adds when it needs it. That is the answer to this plan's
first open question, and it differs per candidate exactly as that question predicted.

| candidate                              | version / date           | KB          | the concern, and who has it                                                                                                                                                                                                      |
| -------------------------------------- | ------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hypothesis`                           | 6.167.0, 2026-08-30      | 1385.9      | Property-based testing. Real shapes here (version arithmetic, parsers), but a testing _style_ a repo opts into, and 1.4 MB with a near-daily release cadence is weight every consumer would carry for a style most will not use. |
| `syrupy`                               | 6.0.0, 2026-08-22        | 56.7        | Snapshot assertions — `scaffoldapy` renders templates and asserts on them by hand. That repo should decide it, which is open question 4.                                                                                         |
| `pytest-httpx`, `respx`                | 0.36.2 / 0.23.1, 2026-04 | 19.8 / 25.0 | HTTP fixtures, for the repos that use httpx. Both **measured to coexist with the socket guard** — see below.                                                                                                                     |
| `time-machine`                         | 3.5.0, 2026-08-25        | 69.7        | Time control, next to the `python-conventions` skill's dates/times topic. Compiled (64 wheels), actively released.                                                                                                               |
| `pytest-subprocess`                    | 1.6.0, 2026-05-10        | 23.2        | Mocking real subprocess calls — relevant to the integration tier, where `MockContext` deliberately does not reach.                                                                                                               |
| `pytest-datadir`, `pytest-regressions` | 1.8.0 / 2.11.0           | 6.4 / 25.0  | Fixture-file management, for a repo whose tests grow fixture-heavy.                                                                                                                                                              |
| `pytest-recording`                     | 0.13.4, 2025-05-08       | 13.4        | VCR-style record/replay. Recording needs network, so it belongs to the integration tier only, never near the offline gate.                                                                                                       |
| `pytest-xdist`                         | 3.8.0, 2025-07-01        | 45.3        | Parallelism. Measurably inert (nothing without `-n`), so it _qualifies_ for the manifest — held back only because this repo's unit tier is 1.0s and no consumer has reported a slow one. Revisit on evidence, not in advance.    |
| `pytest-mock`                          | 3.15.1, 2025-09-16       | 9.9         | The most-installed pytest plugin there is, and it covers no concern this family has: tests use `monkeypatch` and `MockContext` already. Popularity is a tiebreaker, not a reason.                                                |

### Rejected, with the reason

Recorded so a later session does not re-litigate a settled no.

| candidate              | reason                                                                                                                                                                                                                                    |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pytest-sugar`         | **Not inert.** Replaces the terminal reporter entirely under a pty — 193 KB of output where the baseline prints 7.5 KB. The gate's output is read by agents as well as humans.                                                            |
| `pytest-randomly`      | **Not inert.** Reorders every run on install. See open question 3 for the `-p no:randomly` variant, which is the only way it could return.                                                                                                |
| `pytest-asyncio`       | The slot is taken. `anyio` is already resolved family-wide and `pytest.ini` already derives `anyio_mode` per consumer; two async plugins in one environment is a conflict, not a choice.                                                  |
| `pytest-rerunfailures` | Inert, so this is a values rejection rather than a mechanical one: a retry converts a real defect into a slower green run. This family already treats an xpass as a failure and every warning as an error; a rerun flag contradicts both. |
| `pytest-env`           | `monkeypatch.setenv` covers it, per-test rather than per-session, which is strictly better isolation. No uncovered concern.                                                                                                               |
| `pyfakefs`             | The concern (filesystem isolation) is already structural via `tmp_path`, `tmp_cwd` and `isolated_home`. 236 KB to re-answer a solved question.                                                                                            |
| `pytest-check`         | Soft assertions let a test continue past a failed check, which produces tests that report several failures for one cause. No concern behind it here.                                                                                      |
| `pytest-benchmark`     | Adds a banner line, and performance is not a concern any repo in the family has stated. Nothing to measure yet.                                                                                                                           |
| `pytest-order`         | Inert, but explicit inter-test ordering is a dependency between tests — the thing to remove, not to declare.                                                                                                                              |
| `pytest-repeat`        | Inert, but the flake-hunting it serves is an occasional ad-hoc need, met by `--count` on a one-off install.                                                                                                                               |
| `pytest-testmon`       | Inert, but it selects tests from a local DB keyed to a working tree. The unit tier is 1.0s; there is nothing to save and a stale-DB failure mode to acquire.                                                                              |
| `pytest-freezer`       | 8 releases, last 2024-12-12 — effectively parked. `time-machine` covers the same concern and shipped 2026-08-25.                                                                                                                          |
| `pytest-clarity`       | 5 releases, last 2021-06-11, **no wheel at all** (sdist only). Unmaintained.                                                                                                                                                              |

## Open questions

[NEEDS CLARIFICATION: whether a non-inert plugin can be adopted _with_ its behaviour disabled by the
shipped `pytest.ini` — `pytest-randomly` has `-p no:randomly`, for instance. That would make the
inert-by-default rule a property of the config rather than of the plugin, which is a weaker but
possibly acceptable bar. It also puts more behaviour in a file every consumer inherits, which is the
coupling `test-tiers.md` already flags. Moot unless someone wants `pytest-randomly` specifically —
it is the only rejection this would reopen, since `pytest-sugar` has no equivalent switch worth
shipping.]

[NEEDS CLARIFICATION: whether this survey should cover the _generated_ repo's plugins separately.
`scaffoldapy` picks dependencies per interface, so an async plugin for `web_service`/`mcp_server`
may belong in the template rather than in the shared manifest — the same split that repo is working
out for the test tree itself, in its own `plans/2026-08-30-generated-test-layout.md` (filed there
from here on 2026-08-30). `syrupy` above is the concrete case: it is recommended rather than shipped
precisely because that repo, not this one, has the snapshot concern.]

## Resolved by measurement

**The socket guard does not interfere with the HTTP-mocking candidates.** Measured 2026-08-30, both
plugins under the same `disable_socket(allow_unix_socket=True)` the unit tier's `no_network` fixture
installs, with a control test in the same file proving the guard was live (a real `httpx.get` raised
`SocketBlockedError` on `getaddrinfo`). `pytest-httpx`'s `httpx_mock` fixture and `respx.mock` both
served their mocked response and passed. They intercept at the transport layer, so no socket is ever
opened — which was the reasoning, now with a measurement under it.

[PITFALL: `pytest_socket` raises `SocketBlockedError` **and** emits a `UserWarning` with the same
message. Under this repo's `filterwarnings = error` a test that deliberately asserts on a blocked
socket therefore fails on the warning rather than passing on the exception, unless it filters the
warning too. Not a reason against anything — `pytest-socket` is already shipped — but it is the trap
waiting for the first test written to prove the guard works.]

**Whether "standardise" has to mean "in the exported manifest"** is answered per candidate in the
three tables above, which is what this plan asked the survey to produce: one adoption, nine named
recommendations, thirteen recorded rejections.

## Recommended direction

`pytest-timeout` is in the manifest as of 2026-08-30, with its rationale and the `pytest-socket`
warning pitfall in [`../contributing/test-tiers.md`](../contributing/test-tiers.md). Nothing else is
adopted.

What is left of this plan is the **recommendation and rejection tables**, which still have no
permanent home: they belong in `contributing/test-tiers.md` at retirement, and they are the more
valuable half — the adoption was one line, while the "why not `pytest-sugar`" answer is what stops
this being surveyed a third time. Retiring is blocked only on the two open questions above, of which
the second is really `scaffoldapy`'s to answer.

[DEFERRED: this plan proposes no change to the two already shipped. `pytest-cov` and `pytest-socket`
were decided separately and on their own merits; nothing here revisits them.]

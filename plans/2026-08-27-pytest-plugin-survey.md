---
status: idea
updated: 2026-08-27
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

### Candidates worth a real look

Listed as a starting point, not a shortlist — the survey's job is to widen this, and to say why each
rejection is a rejection.

| candidate                               | the concern it covers                                                                          |
| --------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `pytest-timeout`                        | a hung test in the integration tier vs. a CI job that dies at its `timeout-minutes`            |
| `hypothesis`                            | property-based testing — parsers and version arithmetic are the shapes here                    |
| `syrupy` / snapshot testing             | rendered-output assertions, which `scaffoldapy` does by hand today                             |
| `pytest-asyncio` / `anyio`              | async projects; `anyio` already appears in generated web-service venvs via starlette           |
| `pytest-httpx` / `respx`                | HTTP fixtures — and their interaction with the socket guard is the interesting part            |
| `time-machine` / `pytest-freezer`       | time control, next to the `python-conventions` skill's dates/times topic                       |
| `pytest-randomly`                       | catches inter-test dependencies — and is the archetypal _not_ inert plugin                     |
| `pytest-rerunfailures`                  | flaky-test retry, which this family may want to reject on principle rather than on weight      |
| `pytest-xdist`                          | parallelism; this repo's unit tier is under a second, a generated repo's may not stay that way |
| `pytest-datadir` / `pytest-regressions` | fixture-file management                                                                        |

## Open questions

[NEEDS CLARIFICATION: whether "standardise" has to mean "in the exported manifest". A plugin could
instead be a documented recommendation in `contributing/test-tiers.md` that a repo adds when it
needs it. The manifest is the right home for something every repo benefits from having _available_;
a plugin only some repos will ever import may be better as a named recommendation than as weight in
every venv. The answer probably differs per candidate, and the survey should say which bucket each
lands in rather than assuming one.]

[NEEDS CLARIFICATION: whether the socket guard changes the calculus for the HTTP-mocking candidates.
`pytest-httpx` and `respx` intercept at the transport layer, so they should coexist with
`disable_socket()` — a mocked request never reaches a socket — but that is reasoning, not a
measurement, and it is exactly the kind of interaction worth proving before recommending either.]

[NEEDS CLARIFICATION: whether a non-inert plugin can be adopted _with_ its behaviour disabled by the
shipped `pytest.ini` — `pytest-randomly` has `-p no:randomly`, for instance. That would make the
inert-by-default rule a property of the config rather than of the plugin, which is a weaker but
possibly acceptable bar. It also puts more behaviour in a file every consumer inherits, which is the
coupling `test-tiers.md` already flags.]

[NEEDS CLARIFICATION: whether this survey should cover the _generated_ repo's plugins separately.
`scaffoldapy` picks dependencies per interface, so an async plugin for `web_service`/`mcp_server`
may belong in the template rather than in the shared manifest — the same split that repo is working
out for the test tree itself, in its own `plans/2026-08-30-generated-test-layout.md` (filed there
from here on 2026-08-30).]

## Recommended direction

1. **Sweep for concerns with no plugin behind them**, the way the gate-tooling plan did for the
   quality gate, rather than starting from a list of popular plugins and filtering it. Popularity is
   a tiebreaker, not a reason.
2. **Apply the inert-by-default test first**, since it is cheap and it settles several candidates
   without any research at all.
3. **Research to the depth `~/AGENTS.md` asks for** — real config examples and a run against this
   repo, not a single search-summary pass — and judge each package from its own PyPI file list and
   release cadence rather than from a summary. Two measurements in this family have already been
   reversed by doing that (`hadolint-py`, `lychee-bin`).
4. **Record every rejection with its reason**, in the plan and then in `contributing/`. The value of
   this survey is as much "why the family does not use `pytest-sugar`" as which plugins it adds — a
   later session should not re-litigate a settled no.

[DEFERRED: this plan proposes no adoption by itself. `pytest-cov` and `pytest-socket` are already
in, decided separately and on their own merits; nothing here revisits them.]

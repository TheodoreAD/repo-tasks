---
status: in-progress
updated: 2026-08-31
---

# The push-triggered `deps.audit` workflow

## Context

Designed by the 2026-08-26 quality-gate coverage sweep and the one part of it that never landed:
`inv deps.audit` running in CI. It could not be added, because it would have been red from its first
run — `devpi-server`'s `setuptools<=81` (and its `pyramid` dependency's `<82`) held this repo's lock
on a `setuptools` carrying two advisories that nothing here could fix. The deferral was recorded
against the devpi plan rather than worked around, precisely so no suppression list or narrowed CI
scope would bake that pin into shipped code.

**That blocker is gone as of 2026-08-30.** devpi was replaced by pypiserver plus a JSON stub
([`../contributing/test-tiers.md`](../contributing/test-tiers.md), "Package index"), which took the
lock from 98 packages to 63, removed `setuptools` from it entirely, and took `inv deps.audit` to
`Found no known vulnerabilities`. Re-confirmed live 2026-08-31.

The task itself already exists and is already correct — `deps.audit` is `uv audit --locked`, marked
`@requires(NETWORK)`, standalone by rule 1 because its answer changes when the OSV database changes
rather than when the code does
([`../contributing/quality-gate.md`](../contributing/quality-gate.md)). This plan is only about
where and when CI runs it.

The three questions this plan opened were settled by the user 2026-08-31: keep it away from the
network-less gate, run it on `main`, let `main` stay red on a vulnerability, make the security
signal legible separately from the correctness one, and **make it identical in every repo** — the
last being the binding constraint, because per-repo drift is the thing that is hard to track.

## Design

### 1. `.github/workflows/security-reusable.yml` — the job, defined once

`on: workflow_call`, one `audit` job: checkout, `astral-sh/setup-uv`, `uv audit --locked`. No
`./bootstrap.sh`, no venv, no cache.

[DECISION: nothing to cache, measured rather than assumed. `uv audit --locked` reads `uv.lock` and
queries OSV; it needs no installed environment at all — run on a clean `git archive` export with no
`.venv`, it completed in 0.72s wall. The "cached venv over several jobs" question therefore has no
subject: there is no venv, and the job is shorter than restoring a cache would be.]

[DECISION: the raw `uv audit --locked` rather than `inv deps.audit`, which is exactly that command
(`src/repo_tasks/deps.py`). Running the task would mean bootstrapping the whole dev group to shell
out to one uv subcommand, and would restrict the workflow to repos that use `repo-tasks` — the
command form works for any uv project. The cost is the command string living in two places, closed
by a test rather than by discipline (§3).]

### 2. `.github/workflows/security.yml` — the trigger, and the separate signal

`on: push: branches: [main]` plus `workflow_dispatch`. Its only job `uses:` the reusable workflow.

[DECISION: a separate workflow file is how GitHub reports "the code is fine, the dependencies are
not". Every workflow gets its own check run, its own name against the commit, and its own badge, so
`CI ✓` beside `Security ✗` is legible with nothing further configured. This is the whole answer to
"figure out how GitHub reports this" — the fancier route does not survive the uniformity
requirement.]

[DECISION: **SARIF into code scanning was rejected on uniformity, not on effort.** Findings in the
Security tab would be the nicer surface, but code scanning needs a GitHub Code Security licence on
private repositories, and this family is mixed: measured 2026-08-31, five public (`repo-tasks`,
`scaffoldapy`, `power-user-linux-setup`, `agent-skills`, `invoke-stubs`) and four private. So it
would work free on five repos and not at all on four, which is exactly the per-repo difference the
requirement forbids. Secondary: `uv audit --output-format` offers only `text` and `json`, so the
route would also need a SARIF converter nobody in this family maintains.]

[DECISION: a red `main` on an unfixable advisory is the intended outcome, per the user. No
suppression list, no acknowledge-and-move-on. This repo has lived in that state — four days on
`setuptools` — and the alternative is a suppression file that outlives the advisory it silenced.]

### 3. The uniformity mechanism: one definition, called everywhere

Every other repo gets a caller of about six lines,
`uses:
TheodoreAD/repo-tasks/.github/workflows/security-reusable.yml@main`. `repo-tasks` calls its
own copy by path, since it hosts it.

[DECISION: the reusable workflow lives in `repo-tasks` **because `repo-tasks` is public.** On Free,
Pro and Team a reusable workflow must be in the same repository or a public one — so a public host
is callable from the family's private repos, while hosting it in a private repo would need
Enterprise. That is the only reason this file is here rather than somewhere more thematic.]

[DECISION: callers pin `@main`, not a SHA. A pinned ref would have to be bumped in every consumer,
which reintroduces exactly the per-repo drift the reusable workflow exists to remove; both ends of
the call are owned by the same person, so the supply-chain argument for pinning is weak here. zizmor
is content (12 suppressed, no findings).]

The drift that remains is between `deps.py` and the workflow's `run:` line, and it is closed by
`test_deps.py::test_audit_command_matches_the_reusable_workflow`: it asks `deps.audit` what command
it builds, then asserts that exact string appears as a `- run:` step in the reusable workflow.
Change either and the test fails naming the other.

## Files touched

- `.github/workflows/security-reusable.yml` — new, the job.
- `.github/workflows/security.yml` — new, the trigger.
- `tests/unit/test_deps.py` — one new test pinning the command string across both homes.
- `contributing/quality-gate.md` — new section "The dependency audit runs as its own workflow",
  carrying the four decisions and the no-cache pitfall.

## Verification

- `inv quality.precommit` green: 529 unit tests (528 + the new one), basedpyright 0/0.
- `inv quality.workflow-check` green on both new files — actionlint clean, zizmor "No findings to
  report (12 suppressed)". Both files were picked up automatically by `projects.py`'s
  `tracked_files()`, with no glob to update.
- `uv audit --locked` on a clean checkout with no `.venv`:
  `Found no known vulnerabilities and no
  adverse project statuses in 62 packages`, 0.72s.

Confirmed on GitHub, first push to `main` (commit `9933e2a`, run `33339113208`, 2026-08-31):

- The reusable-workflow call resolved — the job reports as `audit / audit`, the caller/callee naming
  GitHub gives a `workflow_call`.
- **`CI` and `Security` appear as two independent runs against the same commit**, both green. That
  is the separate signal this design is for, working: one can go red without the other.
- The whole job took **9s**, of which the audit step was ~1.4s: `Resolved 64 packages in 0.72ms`,
  `Found no known vulnerabilities and no adverse project statuses in 62 packages`.
- The experimental-feature warning appears in the log as expected and as `deps.py` intends — left
  visible rather than silenced with a flag that would break when uv graduates the command.

## What is left

[DEFERRED: **the eight other repos each need their caller file**, and that is per-repo work in repos
this session may not write to. `scaffoldapy` is the highest-leverage one, since its
`template/.github/workflows/` would give every future generated repo the caller for free; the
existing repos each need the same six lines added once. Until then the audit runs in `repo-tasks`
alone, and the uniformity this design is built for is potential rather than actual.]

[DEFERRED: **an advisory that lands with no push here is not seen until the next push.** The obvious
fix is a schedule, and this repo has already ruled one out — `contributing/quality-gate.md`,
"Nothing here runs on a schedule, and that is the decision", settled 2026-08-30: a red scheduled run
has no audience in a repo that pushes straight to `main` and reviews no PRs, and an unwatched
scheduled job looks like coverage without being it. That decision explicitly left the _trigger_
open, which is what landed here. The tension is real and worth revisiting on its own terms rather
than by quietly adding a `cron`: a vulnerability differs from the staleness cases that decision was
about, because nobody has to read a red run for the advisory to matter. Not re-decided here.]

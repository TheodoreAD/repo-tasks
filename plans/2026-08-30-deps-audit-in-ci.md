---
status: landed
updated: 2026-09-04
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
(`src/repo_tasks/deps.py`). Confirmed by the user 2026-09-04 on the criterion "if `inv` is not
installed when you need to run the uv command, then it makes sense not to use invoke" — and it is a
bootstrap-time question, which is what makes that criterion bite. `bootstrap.sh` says so itself: it
exists to get "from a fresh clone (or a CI runner) to a working `inv`, nothing more — the one place
a raw `uv` call is unavoidable, since there's no `inv` to bootstrap with yet". A CI runner starts
with neither, so reaching `inv deps.audit` means running `uv run inv venv.create` first and syncing
the entire dev group to shell out to one uv subcommand. It would also restrict the workflow to repos
that use `repo-tasks`, where the command form works for any uv project. The cost is the command
string living in two places, closed by a test rather than by discipline (§3).]

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

Every other repo gets a caller of about six lines, whose one meaningful line is a job-level `uses:`
naming `TheodoreAD/repo-tasks/.github/workflows/security-reusable.yml` at a full 40-character commit
SHA, with the readable version beside it in a trailing comment. `repo-tasks` calls its own copy by
relative path instead, which takes no ref at all and is why nothing in this repo pins anything.

[DECISION: the reusable workflow lives in `repo-tasks` **because `repo-tasks` is public.** On Free,
Pro and Team a reusable workflow must be in the same repository or a public one — so a public host
is callable from the family's private repos, while hosting it in a private repo would need
Enterprise. That is the only reason this file is here rather than somewhere more thematic.]

[DECISION: **callers pin a full SHA, not `@main`** — the user's call, 2026-09-04, on stability. The
first draft of this plan chose `@main` and recorded it as settled; that was a live trade-off decided
without asking, and this replaces it. A moving ref changes every consumer's audit the moment this
repo's `main` moves, including in repos nobody is touching; a SHA means a consumer runs what it was
pinned to until someone changes it on purpose. `ci.check-actions` already understands the shape — it
parses a job-level `uses:`, recognises a 40-hex SHA and reads a trailing `# <version>` comment — but
see the pitfall below for why that does not help yet.]

[PITFALL: the pin is currently unwatched. `ci.check-actions` resolves currency through
`gh api repos/<owner>/<repo>/releases/latest`, and this repo has **no tags and no releases** — so
its own reusable workflow is treated as "nobody's release to track" and skipped. A pinned consumer
therefore goes stale silently. Tagging releases here would close it, and that is coupled to the
still-open `plans/2026-08-22-pypi-publish-integration.md`.]

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

## What is left, and where each piece now lives

Nothing is left in this plan. Both deferrals were rehomed 2026-09-04 into plans that stay.

- **The eight other repos each need their caller file**, and that is per-repo work in repos this
  session may not write to — so until it happens, the audit runs in `repo-tasks` alone and the
  uniformity this design is built for is potential rather than actual. `scaffoldapy` is the
  highest-leverage one, since its `template/.github/workflows/` would give every generated repo the
  caller for free, and it was already filed there as `plans/2026-08-31-security-workflow-caller.md`.
  The other seven are now an item in
  [`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md), which owns the batched
  cross-repo pass.
- **An advisory that lands with no push here is not seen until the next push.** Moved to
  [`2026-09-04-scheduled-dependency-audit.md`](2026-09-04-scheduled-dependency-audit.md), which
  states the tension with the no-schedule decision properly and adds the option this plan never
  priced — Dependabot alerts, which may make the schedule argument moot rather than winning it.

## Migrated to

- [`../contributing/quality-gate.md`](../contributing/quality-gate.md), "The dependency audit runs
  as its own workflow" — written when the work landed rather than at retirement, and it already
  carries the four decisions and the unwatched-pin pitfall: why a separate workflow rather than
  SARIF into code scanning (a licence this family's four private repos do not have, so it would work
  on five repos and not four), why the reusable workflow lives in this repo (a public host is
  callable from private repos on Free/Pro/Team), why callers pin a full SHA rather than `@main`, and
  why the pin currently goes stale silently.
- `tests/unit/test_deps.py::test_audit_command_matches_the_reusable_workflow` — the command string
  living in two places is closed by that test rather than by this document. It asks `deps.audit`
  what command it builds and asserts that exact string appears as a `- run:` step in the reusable
  workflow, so changing either fails naming the other.

**Deliberately not migrated.** The verification section — the 9s job,
`Resolved 64 packages in
0.72ms`, the `audit / audit` naming GitHub gives a `workflow_call` — is a
record that it worked once, and the workflow running on every push to `main` is the standing version
of that claim. The no-cache decision's measurement (0.72s on a clean export with no `.venv`) is
kept, because it is the reason a future reader should not add a cache, and that reason is not
visible from the workflow file.

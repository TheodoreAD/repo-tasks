---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/invoke-stubs
source_session: 76d98521-8e7c-4524-bb4f-4caeb36e8cb0.jsonl
source_moment: 2026-09-28
source_plan:
---

# `ubuntu-latest` becomes Ubuntu 26.04 from 2026-10-19, family-wide

**Deadline: the rollout starts 2026-10-19 and completes by 2026-11-19.**

## Context

GitHub's announcement is actions/runner-images#14748 (2026-09-17). `ubuntu-latest` moves from
24.04.5 to 26.04.1. The mitigations: pin `ubuntu-24.04`, or use `ubuntu-26.04` to test ahead. Every
run annotates the notice, and it was first read on invoke-stubs' first CI run 2026-09-28.

Every Linux job in the family is on `ubuntu-latest`: repo-tasks (`ci`, `canary`, `publish`,
`release`, `docker-release`, and `security-reusable`, which every consumer's audit runs on),
scaffoldapy and its `template/`, ingesta, agent-skills, invoke-stubs, mkdocs-taudelta, and
power-user-linux-setup.

**power-user-linux-setup is the exception, filed separately** as
`2026-09-28-ci-stops-testing-24-04-when-ubuntu-latest-moves.md`. It targets an OS, so for it the
move is a product decision. Everything else here gets Python from uv (`setup-uv` plus
`.python-version`), so the runner OS should be incidental. That is expected, not measured.

## Open questions

[NEEDS CLARIFICATION: float or pin, for the uv-based repos? Floating (keep `ubuntu-latest`) is what
the template does now and costs nothing, but a break would show up as a red run on some unrelated
push during the rollout weeks. Pinning `ubuntu-24.04` is stable, but it is one more version that
rots, and nothing reports it the way `ci.check-actions` reports actions. The likely answer is float,
after one run on 26.04 to check the expectation above.]

## Measuring the risk of 26.04 over 24.04

The float-or-pin answer should rest on these numbers, not on the expectation above. Two halves:
static, what the runner provides that the family actually uses, and dynamic, what the jobs do on
each image.

1. **What the family takes from the runner rather than from uv.** Grep every family workflow and
   `repo_tasks`' `c.run(...)` calls for binaries that are not installed by uv or a wheel: `git`,
   `gh`, `docker` (for `test.workflows` via act, and `docker-release`), `bash`, `curl`, anything
   `apt`. Wheel-shipped tools are the same on both images (`basedpyright` and its node,
   `shellcheck-py`, `shfmt-py`, `actionlint-py`, `zizmor`), and so is Python, which comes from
   `.python-version`.
2. **Those binaries' versions on each image.** Read them from the two image manifests,
   `images/ubuntu/Ubuntu2404-Readme.md` and `Ubuntu2604-Readme.md` in actions/runner-images. Clone
   that into `$RESEARCH_HOME` rather than fetching pages. Record a table: binary, 24.04 version,
   26.04 version, and whether any family code depends on behaviour that changed between them.
3. **Every job on both images.** In each repo with CI, a temporary `runs-on: ${{ matrix.os }}` with
   `os: [ubuntu-24.04, ubuntu-26.04]` and `fail-fast: false`, triggered once by `workflow_dispatch`
   or a throwaway branch, then reverted. Record per repo and job: pass or fail on each image,
   duration on each, and any warnings or annotations that appear on only one. repo-tasks goes first,
   because `canary.yml` also exercises scaffoldapy's generated output. `security-reusable.yml`
   counts too: every consumer's audit runs on it.
4. **Decision rule, written down before the numbers come in:**
   - All green on 26.04 with no new warnings: float, and write in the template's `ci.yml` that this
     was measured and when.
   - A failure traced to the OS: pin `ubuntu-24.04` in the template, sweep the pin to the consumers
     before 2026-10-19, and open a plan for the 26.04 fix, with this table as its evidence.
   - A failure that is not reproducible on a re-run: note it, and re-run once more rather than
     pinning on one flake.

## Recommended direction

Run the measurement above before 2026-10-19, starting with one repo's full CI on `ubuntu-26.04`.
repo-tasks itself is the natural choice, because `canary.yml` already exercises scaffoldapy's
generated output, and a temporary job or a `workflow_dispatch` input would do it. If it is green,
keep floating and say so in the template's `ci.yml` comment, so the next announcement is not
re-litigated. If it is red, pin `ubuntu-24.04` in the template and sweep it to the consumers, then
plan the 26.04 fix. invoke-stubs' `ci.yml` follows whatever the template decides.

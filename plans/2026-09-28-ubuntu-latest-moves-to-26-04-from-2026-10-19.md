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

## Measured 2026-09-28, repo-tasks

A throwaway branch, `measure/ubuntu-26-04` (commit `614f687`, deleted afterwards), added itself to
the push triggers of CI, Canary and Security. It ran every Linux job there on an
`os: [ubuntu-24.04, ubuntu-26.04]` matrix. The publishing workflows (`publish`, `release`,
`docker-release`) were deliberately not run.

**Dynamic: every job green on both images.**

| workflow / job                        | 24.04             | 26.04                 |
| ------------------------------------- | ----------------- | --------------------- |
| CI `quality`                          | pass, 23s         | pass, 56s (see below) |
| CI `unit` 3.11 / 3.12 / 3.13 / 3.14   | pass, 14–18s each | pass, 17–21s each     |
| Canary `scaffoldapy`, 10 real renders | pass, tier 84.5s  | pass, tier 93.5s      |
| Security `audit` (every consumer's)   | pass, 9s          | pass, 8s              |
| annotations on any job                | none              | none                  |

- The 26.04 `quality` job's own log starts 36s after GitHub marks it started, and its work took
  about 19s. So the gap is runner assignment, presumably a smaller 26.04 pool before the rollout,
  not the gate.
- The empty annotations are real, not a failed read. `main`'s own `ubuntu-latest` jobs from the same
  hour each carry
  `notice | The ubuntu-latest label will migrate to Ubuntu 26 beginning October 19,
  2026`, read
  through the same API call. That notice is the only annotation either image produces.
- **uv uses the image's system Python whenever it matches the request.** On 26.04 the 3.14 job ran
  `/usr/bin/python3.14`, which is 3.14.4. Every other job got a uv-managed interpreter, except 3.12
  on 24.04, which already runs the system 3.12.3 today. So this is not new behaviour, and it passed.

**Static: runner-provided tools**, from `images/ubuntu/Ubuntu2404-Readme.md` and
`Ubuntu2604-Readme.md` in actions/runner-images (`main@055a621`, in `$RESEARCH_HOME`, image versions
20260920):

| tool          | 24.04                  | 26.04                 |
| ------------- | ---------------------- | --------------------- |
| OS / kernel   | 24.04.5 / 6.17         | 26.04.1 / 7.0         |
| bash          | 5.2.21                 | 5.3.9                 |
| git           | 2.55.0                 | 2.55.0                |
| gh            | 2.101.0                | 2.101.0               |
| curl          | 8.5.0                  | 8.18.0                |
| Docker        | 28.0.4, Compose 2.38.2 | 29.4.2, Compose 5.1.3 |
| OpenSSL       | 3.0.13                 | 3.5.5                 |
| jq            | 1.7                    | 1.8.1                 |
| system Python | 3.12.3                 | 3.14.4                |

`bootstrap.sh` and `bootstrap-repo-tasks.sh` use none of curl, wget, docker, sudo or apt, so what
the gate takes from the runner is bash and git: bash moves a minor version and git is identical.
Docker's major and Compose's jump matter only to `docker-release`, which was not run.

[PITFALL: **pinning `ubuntu-26.04` would turn every gate red today.** actionlint 1.7.12, the
family's locked version and also upstream `main` as of its last commit 2026-04-19, does not know the
label: `label "ubuntu-26.04" is unknown … [runner-label]`. The measurement branch needed a
`.github/actionlint.yaml` declaring it. Floating `ubuntu-latest` never names the label, so it is
untouched, which is one more point for floating.]

Not measured: the other repos' own CI (ingesta, agent-skills, invoke-stubs, mkdocs-taudelta, and
scaffoldapy's own). Their jobs are the same uv-and-bootstrap shape the CI and Canary jobs above
exercise. Canary runs scaffoldapy's generated repos' full gate, which is what every template
consumer runs. power-user-linux-setup is its own plan.

By the decision rule above, **all green with no new warnings means float**.

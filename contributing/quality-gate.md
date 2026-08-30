# What the gate checks, and why each tool is in it or beside it

`inv quality.check` runs ruff (lint + format), dprint, basedpyright, shellcheck, shfmt, actionlint,
zizmor, hadolint, `deps.check`, `docs.link-check`, `test.untested-modules`, and the unit tier. How
each of those is _configured_ is a separate question, answered in
[`type-checking.md`](type-checking.md), [`test-tiers.md`](test-tiers.md), and
`power-user-linux-setup`'s
[`contributing/quality-tooling.md`](https://github.com/TheodoreAD/power-user-linux-setup/blob/master/contributing/quality-tooling.md).
This file answers the other one: **which classes of problem does the gate look for, which are
deliberately checked from outside it, and which are not checked at all.**

The two rules that decide in-or-out are in
[`task-module-conventions.md`](task-module-conventions.md#declare-what-a-task-needs-beyond-a-checkout)
— the chain stays deterministic and offline, and anything outside it declares what it needs. What
follows is how each tool falls out of them.

Everything in `check` ships to every consumer through `repo-tasks-quality`, so each addition is a
dependency added to `power-user-linux-setup`, `scaffoldapy`, and every generated repo — see
[`consumer-sweep.md`](consumer-sweep.md).

## In the gate

**`deps.check` (`uv lock --check`)** — a `pyproject.toml` edit without a re-lock used to pass
`precommit` locally and fail in CI, where `bootstrap.sh`'s `uv sync --locked` catches it by
accident. It is offline, deterministic, and needs no `.venv`, so the gate is where it belongs and
the local/CI divergence closes.

**zizmor, folded into `workflow_check` rather than given its own task.** actionlint covers workflow
correctness and nothing covered workflow security, which matters here because `publish.yml` carries
`id-token: write` against PyPI Trusted Publishing. zizmor's online audits are opt-in behind a token,
so the offline default qualifies.

[DECISION: one task per question the developer asks ("are my workflows OK?"), not one per binary.
The precedent is `format_check`, which runs ruff and dprint under one name. Both tools file-gate on
the same `.github/workflows/*.yml` list, so the no-op-cleanly contract is unchanged.]

[PITFALL: `--offline` is passed explicitly even though it is already the default. zizmor enables its
online audits whenever `GH_TOKEN`/`GITHUB_TOKEN` is in the environment, which is the normal state
inside CI — without the flag the gate's rule set differs between a laptop and a runner.]

**hadolint (`quality.dockerfile_check`)**, file-gated on tracked `Dockerfile`/`*.Dockerfile` paths,
with `require_tool("hadolint")` inside the branch exactly as `shell_check` does.

[DECISION: hadolint and `docker build --check` are not substitutes, and both are adopted at
different tiers. Measured: Docker's built-in checks are 21 rules, almost entirely build semantics
and casing (`StageNameCasing`, `FromAsCasing`, `LegacyKeyValueFormat`, `UndefinedVar`,
`CopyIgnoredFile`, `SecretsUsedInArgOrEnv`). hadolint is ~100 `DL####` rules plus embedded
ShellCheck over every `RUN` body — apt pinning, `apt-get update` layer merging,
`--no-install-recommends`, `ADD` vs `COPY`, `latest` base tags, root user. For a
`debian:bookworm-slim` + apt + non-root-user image, hadolint's slice is the one with findings in it;
Docker's slice is real but needs a daemon, so it lands in the integration tier instead.]

No `.hadolint.yaml` until a suppression is actually needed, matching the `.shellcheckrc` posture: an
exclusion lands in the file with an inline reason, following kubernetes' precedent, rather than as a
flag on the call. The accepted cost is ~12 MB in every consumer's venv, including consumers with no
Dockerfile — the same dependency-weight concern as `plans/2026-08-24-devpi-dependency-weight.md`.

**`docs.link_check`, hand-rolled.** Extracts markdown links, resolves the relative ones against the
containing file, asserts each target exists. Relative file links only — not external URLs, not
anchors, not HTML. It earns a gate slot because the `plan-docs` retirement procedure requires the
finishing grep to return no live pointers and nothing enforced it: the first revision of the plan
that proposed this task shipped two dangling citations to a plan retired in the same session.

[DECISION: hand-rolled rather than lychee, against the usual "prefer the maintained external
project" default, on two measured facts. `lychee-bin` — the only maintained PyPI wrapper — is a 78.1
MB manylinux x86_64 wheel, 6.5× hadolint's, shipped to every consumer for link checking. And it has
exactly one release ever (0.24.2, seventeen minutes after upstream's own `lychee-v0.24.2`): current
with upstream today, but a single data point is not a version-tracking record. The lighter prior art
is dead — `pytest-check-links` last released 2024-04, `linkcheckmd` 2021-02. The need is narrow
enough that ~40 lines covers it.]

**`test.untested_modules`** — every module under `src/<pkg>/` has a `tests/unit/test_<module>.py`.
Deterministic, offline, no-ops cleanly where either directory is absent.

[DECISION: the file-existence check is the gate half and coverage is the report half, not the other
way round. The unit tier is `MockContext` command-string assertion, so a line-coverage number
largely measures how much mocking was written — [`test-tiers.md`](test-tiers.md) records two real
`dist.py` bugs that survived full unit coverage. A threshold on that number is metric-gaming waiting
to happen. "Which module has no tests at all" is the question with a true answer.]

## Standalone, by rule 1

**`deps.audit` (`uv audit`, OSV-backed).** The result changes when the OSV database changes, not
when the code does, so a gate step would fail a commit that changed nothing — and would make
`precommit` require network in every consumer. This is the case that motivated rule 1.

[DECISION: `--locked`, not a re-resolve. It audits exactly what `uv.lock` commits to, which is what
a consumer actually installs, and it keeps `deps.py`'s single-writer discipline intact — `lock` is
the only task that may rewrite the lock file. A re-resolving audit would report on a dependency set
nobody has.]

[DECISION: no suppression mechanism. A vulnerable transitive with no fixed version stops the task
loudly, matching "stop loudly and say what to run next". An ignore list would be a second place
where "which advisories do we accept" lives, with no expiry. Build one only when a real unfixable
advisory blocks work — and note that one already has, without moving this decision: see
`plans/2026-08-24-devpi-dependency-weight.md`.]

**`docker.check`** (`docker build --check`) needs a daemon, so it is standalone and exercised from
the integration tier, which already builds both images for real.

**`test.coverage`** — `pytest --cov`, report only, no `--cov-fail-under`; see the decision above.

**`quality.verify_types`** — `basedpyright --verifytypes repo_tasks`, a completeness report over the
public surface that `py.typed` and `invoke-stubs` make a public contract. Its output is a report,
and a consumer package's own completeness is not this gate's business. The half that _is_ enforced
is `tests/unit/test_types.py`, whose `assert_type` assertions pin what a consumer actually sees —
that `@task` preserves the decorated function's signature, and that `from invoke import task`
resolves as a public re-export. Those are the two gaps `invoke-stubs` exists to close
([`type-checking.md`](type-checking.md)); without them a stub regression surfaces only as noise in
every consumer.

**`ci.status`** — recent Actions runs for a branch and whether any failed, wrapping `gh run list`.
It exists because push-triggered CI on a repo with direct-to-main pushes fails silently: nobody
watches the Actions tab.

[DECISION: standalone, not wired into `gitflow`'s push paths. gitflow's `--push` steps cover the
release flow, which is not where these pushes happen — direct pushes to `main` are. A preflight in
gitflow would guard the path that needs it least.]

## What the gate's shipped configs commit every consumer to

`pytest.ini`, `ruff.toml`, and `zizmor.yml` exist twice: the root copy governs this repo and
`src/repo_tasks/configs/` is the shipped canonical copy. Changes land in the root copy, then
`inv configs.promote --apply`.

**`zizmor.yml` had to become a shipped config at all** because since zizmor v1.20.0 the default
`unpinned-uses` policy is a blanket hash-pin, which contradicts the decision below to pin
`publish.yml` and nothing else. The policy is expressible only in a config file — there is no CLI
flag — so leaving it unshipped would have turned every consumer's gate red over a choice they did
not make. `"*": ref-pin` is the encoding.

**`pytest.ini`'s `filterwarnings = error`** is family-wide by design, and each `ignore:` line lands
in that same shipped file with its reason inline.

[DECISION: ignores go in the shared shipped file rather than triggering the unbuilt
`configs.local.toml` mechanism. The dependency set behind these warnings is family-uniform (invoke,
uv, pytest, bump-my-version), so a warning that needs silencing almost certainly needs it
everywhere. `configs.local.toml` stays a spec until something genuinely repo-specific appears.]

[PITFALL: the coupling that buys is real — an upstream deprecation lands and every repo in the
family goes red at once, unblocked only by an ignore landing here, a version bump, and
`configs.pull` in each consumer. It was a reasonable bet because the baseline was zero, and it has
already cost twice: the `scaffoldapy` sweep turned copier's `DirtyLocalWarning` into 21 failures
there and starlette's `TestClient` deprecation into a collection error in every generated web
service. A **consumer's own dependencies are exactly where "family-uniform" stops holding**, and
both fixes were rightly local — a scoped `catch_warnings`, and `httpx2` in the web-service
template.]

[DECISION: `httpx2` over suppressing the starlette warning. It is upstream's own instruction rather
than a workaround, `web_service` with `fetch_strategy = none` pulls in no other HTTP client so it
adds exactly one package, and FastAPI's `TestClient` with `httpx2` installed was verified to pass
under `-W error`. Suppression would have left every generated web service on a deprecated path with
a filter hiding the notice.]

**`ruff.toml`'s `select`** carries `PT` (flake8-pytest-style), `FURB` (refurb), and `PGH`
(blanket-suppression hygiene), select-then-triage as with `PL`/`TRY`: turn on, run, ignore
individual codes with a stated reason rather than pre-guessing.

[DECISION: `PT` is the one that matters most for this repo's shape — a fixture-dense suite in the
hundreds of tests. Its contested rules (ruff #8796) get ignored individually after seeing real hits.
`ERA` was considered and dropped: this family's prose-comment density makes commented-out-code
detection a false-positive generator.]

## Workflow hardening

`ci.yml` carries `permissions: contents: read`, `concurrency` with `cancel-in-progress`,
`timeout-minutes` on each job, and a second job running `inv test.unit` across a 3.11–3.14 matrix.
The `quality.check` job stays single-version — the matrix exists to make
`requires-python = ">=3.11"` a true claim, and the unit tier is sub-second with no Docker, so four
of them cost nothing.

[DECISION: SHA-pin `publish.yml` only, not every workflow, and no dependabot. That file is the one
holding `id-token: write` against Trusted Publishing, so it is where a compromised action would
actually cost something. Pinning everywhere without dependabot means pins rot; adding dependabot
means a recurring PR stream on repos whose owner pushes straight to `main` and reviews no PRs. One
file's pins are maintainable by hand.]

[PITFALL: `enable-cache` on `astral-sh/setup-uv` looks like a missing option and is not one. Its
default is `auto`, which already enables the cache on GitHub-hosted runners for exactly the `push`
and `pull_request` events this workflow uses — it is disabled only for release/tag,
`pull_request_target` and `workflow_run` events, and on self-hosted runners. Read an action's own
input defaults before recording a missing-option finding.]

What zizmor found on its first run, all fixed on their merits rather than suppressed: `artipacked`
(every checkout left the job token in `.git/config`), `template-injection` (`${{ inputs.project }}`
pasted into a `run:` block in a job holding `packages: write`), `excessive-permissions`
(`id-token: write` at workflow level in `publish.yml`), and `cache-poisoning` (`setup-uv`'s `auto`
cache is off for a tag push but on for the `workflow_dispatch` path in the same file).

## Considered and not adopted

Recorded so a later sweep does not re-litigate them:

- **`pre-commit`** — a second runner, config format and mental model beside invoke, which already
  aggregates tools behind one command. `~/AGENTS.md`'s rule against mechanisms that fire behind an
  agent's back reinforces it.
- **gitleaks / secret scanning** — unnecessary here. GitHub's own `secret_scanning` and
  `secret_scanning_push_protection` are enabled on this repo, and Trusted Publishing means no PyPI
  token exists to leak. Push protection is the layer that matters; a gate-side scanner would be
  redundant weight in every consumer.
- **`yamllint` / `taplo lint`** — YAML's two real surfaces here are workflows (actionlint, zizmor)
  and Helm charts (`helm lint`), both already covered by purpose-built tools. A general linter would
  add noise, not coverage.
- **License compliance** — permissive throughout, personal repos. Revisit if a consumer goes
  corporate.
- **`configs.diff` as a gate step** — read-only, so it dodges the silent-mutation objection that
  keeps `configs.pull` standalone, but this repo's root config files are _deliberately_ allowed to
  lead the packaged copies; that is what `configs.promote` is for. A gate step would fire on the
  state the design calls normal.
- **The `S`/bandit family** — rejected wholesale as noise, with one slice still open; see
  `plans/2026-08-30-deferred-gate-tools.md`.
- **deptry** — run ad hoc and it earned its keep, but adoption is still open for the same reason;
  same plan.

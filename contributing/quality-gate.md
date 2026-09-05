# What the gate checks, and why each tool is in it or beside it

`inv quality.check` runs ruff (lint + format), dprint, basedpyright, shellcheck, shfmt, actionlint,
zizmor, hadolint, `deps.check`, `docs.link-check`, `test.untested-modules`, and the unit tier.
`inv quality.precommit` runs `fix`, then that, then `docs.build`. How each of those is _configured_
is a separate question, answered in [`type-checking.md`](type-checking.md),
[`test-tiers.md`](test-tiers.md), and `power-user-linux-setup`'s
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

## What the gate prints

**By default, exactly what invoke prints**: each command echoed, its output streamed, and
`UnexpectedExit` on a failure. That is what a human at a terminal and a CI runner both get, and this
package configures nothing at all to achieve it.

**Under `REPO_TASKS_RUN_REPORT`**, every command run with `echo=True` collapses to one delimited
line, its output folded on success and replayed whole on failure, with the gate's verdict last:

```
ruff check . | ok | 0.0s | All checks passed!
ruff format . | ok | 0.0s | 1 file reformatted
basedpyright | ok | 2.5s | 0 errors, 0 warnings, 0 notes
uv lock --check | ok | 0.0s | Resolved 64 packages in 1ms
pytest | ok | 1.4s | 592 passed in 1.27s
quality.precommit | PASS | 15 steps | 4.4s
```

```
ruff check . | FAIL | exit=1 | 0.0s
F401 [*] `os` imported but unused
 --> bad.py:1:8
...
Found 2 errors.
FAIL | ruff check . | exit=1 (output above)
```

`runner.py` owns the shape and carries the short form of every decision below.

[DECISION: **stock invoke is the default; report mode is opt-in through the environment** — the
user's call, 2026-09-05, on the rule of least surprise, replacing a fold-by-default design landed
hours earlier the same day. That design changed what every consumer saw on upgrade having asked for
nothing; it reached eleven of ~90 `c.run` call sites, so `deps.check` reported a line while
`deps.lock` streamed; and it turned `UnexpectedExit` into `Exit` for everyone.

The measurement behind the old default survives the flip intact, and that is the whole argument.
Over the seven days to 2026-09-05, across every consumer (60 sessions, 14,611 Bash calls), 812 of
1,396 `inv quality.*` runs — 58% — were piped through `head`/`tail`, 466 asking for the last few
lines of a ~50-line success. **All of them were agent sessions**, and that population already runs
under a `CLAUDECODE`-guarded `zshenv` snippet in `power-user-linux-setup` that sets `PIPE_FAIL` for
exactly the same reason. Setting the variable there means the session that would never reach for a
flag does not have to: agents get the report, humans and CI get stock invoke. The old design
conflated "the default" with "what agents get" because it had no mechanism to separate them.]

[DECISION: a `Local` subclass swapped in through `config.runners.local`, not a wrapper at each call
site and not a monkeypatch. `Context.run` builds its runner from that key and the stock config
already holds `Local` there, so it is invoke's own extension point. One line reaches all ~90 call
sites, which is what makes the output uniform where the previous design's eleven hand-wrapped steps
were not.]

[DECISION: the trigger is `echo=True`, so the report line **replaces** the echo line. That flag is
already this package's marker for "a command with an effect the caller should see"
([`task-module-conventions.md`](task-module-conventions.md)), while internal queries pass
`hide=True` and stay silent. No list to maintain, and a new task gets reporting by following the
convention it would follow anyway.]

[DECISION: a call site opts out by **mentioning `hide` itself** — `test.coverage` and the
integration tiers pass `hide=False`. An added kwarg was not available: invoke's
`_unify_kwargs_with_config` raises `TypeError` on any unknown `run` kwarg, so a call site carrying
one would break under stock invoke, which is the behaviour this whole design protects. `hide=False`
is invoke's own interface and a semantic no-op when the mode is off.]

[PITFALL: which makes `hide=False` read as redundant, and a later reader will delete it — silently
folding away the coverage report that is the task's entire purpose. `test_testing.py` asserts it on
every such call for that reason.]

[DECISION: the fourth column is the **last non-empty line of the tool's own output**, generic across
every command rather than parsed per tool. This replaces the pytest-specific count parser and the
former decision that pytest's `N passed` was the only number read out of a tool's output. Measured
over this gate 2026-09-05: five of nine commands print exactly one line on success and it _is_ their
summary (`All checks passed!`, `96 files already formatted`, `0 errors, 0 warnings, 0 notes`,
`Resolved 64 packages in 1ms`, `1 file reformatted`), three print nothing at all, and only pytest
prints more — nine of its ten lines being progress noise. So "does folding hide the output" answers
"only where the output was noise", and a generic rule reads no tool's format, so nothing breaks when
one of them changes its wording.]

[DECISION: on a `warn=True` call the line reports `exit=N` with **no `FAIL` token**, and does not
raise. `warn=True` already means the caller owns the exit code — pytest's exit 5 ("no tests
collected") is a pass in a repo with no tests yet, and calling it a failure would describe something
that never happened. The output is still replayed, because `deps.lock` scrapes stderr for uv's
moved-member hint and needs the failure visible above its own message.]

[DECISION: the verdict names the **command**, not the task. `FAIL | ruff check . | exit=1` is what
to re-run. The gate's name appears on the PASS line only, because that is the one printed by the
gate's own body — invoke stops at the first failing pre-task, so no code that knows which gate is
running ever executes on a red run. `verdict` is gated on the ledger rather than on the environment,
so there is one switch and not two that can disagree.]

[DECISION: the command comes **first** on the line, against the `FAIL | exit=1 | …` shape the user
first proposed and then chose against, 2026-09-05. Command-first is pre-printable — the runner
writes `basedpyright |` before starting and completes the line after — so a hung or killed step
names itself. Status-first cannot, and a silent hang is exactly what cost this package five days on
`docker login` ([`task-module-conventions.md`](task-module-conventions.md)). Greps stay clean either
way: `rg '\| FAIL \|'`.]

[DECISION: `precommit` inlines `check`'s steps (`pre=[fix, *_CHECKS, docs_build]`) rather than
nesting `check`. Nested, `check`'s body would print its own verdict in the middle of a precommit run
with a step count that includes `fix`'s — and the whole property is that the verdict is the last
line. The behaviour is identical; only the chain is flat.]

[PITFALL: the replay writes stdout to stdout and stderr to stderr, flushed at each hand-off. Under
`2>&1 | tail` a block-buffered stdout and an unbuffered stderr otherwise arrive out of order, and
the verdict has to be last. Everything else on the failure path is flushed as it is printed, for the
same reason.]

[PITFALL: `Exit` rather than a re-raised `UnexpectedExit`, but only in report mode.
`UnexpectedExit.__str__` prints just the last ten lines of hidden output inside an "Encountered a
bad command exit code!" template, so letting it through would append a lossy duplicate after the
full replay. Under stock invoke it propagates untouched.]

[PITFALL: a swapped runner is invisible at the call site. Someone asking where their output went
finds nothing in `quality.py` — the answer is an env var set in a shell profile in another repo.
That is the price of the zero-call-site-churn property, and it is not fully mitigable.]

[PITFALL: a consumer that hand-builds its own `Collection` from individual modules instead of
`from repo_tasks import ns` never receives the `ns.configure` call, so report mode does nothing for
it, with no error. Declare `{"runners": {"local": ReportingLocal}}` on your own root collection.
Reaching those consumers would mean patching `Config.global_defaults`, which is the unsupported
monkeypatch this design avoids.]

[PITFALL: `pipefail` in the agent shell (landed the same day, in `power-user-linux-setup`) is what
makes `inv quality.check 2>&1 | tail -3` exit 1 on a red run; report mode is what makes those three
lines say why. Neither substitutes for the other. Verified together 2026-09-05 — the tailed red run
showed `FAIL | ruff check . | exit=1 (output above)` and the Bash tool reported exit 1.]

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
Dockerfile — the same dependency-weight concern that eventually cost devpi its place in the
integration tier ([`test-tiers.md`](test-tiers.md), "Package index").

**`docs.link_check`, hand-rolled.** Extracts markdown links, resolves the relative ones against the
containing file, asserts each target exists and that any `#fragment` names a heading that is still
there. Relative links only — not external URLs, not HTML. It earns a gate slot because the
`plan-docs` retirement procedure requires the finishing grep to return no live pointers and nothing
enforced it: the first revision of the plan that proposed this task shipped two dangling citations
to a plan retired in the same session.

It checks **anchors** as well as files, which is the half a rename breaks: `file.md#heading` used to
verify the file and never the heading.

[DECISION: an anchor resolves against the **union** of two sluggers, and a link passes if either
matches. The same markdown has two renderers in this family — a docs site through python-markdown's
`toc` extension, and `plans/`, `contributing/`, `AGENTS.md` and every README read on github.com —
and they agree on the common case while differing on punctuation and space runs. Requiring either
alone reports correct links in the other renderer as broken. Duplicate headings are suffixed both
ways too: python-markdown appends `_1`, github.com appends `-1`.]

[DECISION: this stays in `link_check` rather than being left to `docs.build`, even though
`zensical build --strict` also catches a dangling anchor. They are not substitutes and neither
subsumes the other — and they are not even in the same half, since the anchor check is offline and
read-only where the build writes a site, so only this one is in `check`. The strict build sees only
a repo that _has_ a docs site, and only the pages inside it; `link_check` sees every tracked
markdown file, which for most consumers — `repo-tasks` included — is all of them, and is where
`plans/` and `contributing/` cross-references live. The strict build catches things anchors cannot,
such as an unresolved nav entry, so both earn their place.]

[PITFALL: three slugger bugs, all of them found by measurement rather than by reading. `_` is an
identifier in these docs and not emphasis — stripping it turns `config_files` into `configfiles`, an
anchor no renderer emits. github.com does **not** collapse runs of spaces, so
`## Bash & the CLI allowlist` drops the ampersand and keeps both surrounding spaces, leaving a
double hyphen. And a single duplicate counter shared between the two sluggers counts every heading
twice, numbering a repeated `## Notes` as `notes_2`/`notes-3`. The first two reported correct links
as broken; the third was caught by the test written for duplicate handling. All three ship as
regression tests.]

[DECISION: hand-rolled rather than lychee, against the usual "prefer the maintained external
project" default, on two measured facts. `lychee-bin` — the only maintained PyPI wrapper — is a 78.1
MB manylinux x86_64 wheel, 6.5× hadolint's, shipped to every consumer for link checking. And it has
exactly one release ever (0.24.2, seventeen minutes after upstream's own `lychee-v0.24.2`): current
with upstream today, but a single data point is not a version-tracking record. The lighter prior art
is dead — `pytest-check-links` last released 2024-04, `linkcheckmd` 2021-02. The need is narrow
enough that ~40 lines covers it.]

**`docs.build` (`zensical build --strict`)**, file-gated on `mkdocs.yml` — **in `precommit`, not in
`check`.** It is what a repo with a published site gets beyond `link_check`: everything the renderer
itself objects to, an unresolved nav entry included.

[DECISION: taken 2026-09-04, after a dangling anchor shipped a red Pages deploy twice in one
consumer. A heading rename changed an anchor while another page kept linking to the old one; `CI`
passed green on both commits while `Deploy docs to GitHub Pages` failed on both, so the branch moved
twice with the published site serving the last good build. At the time this was the only check in
the family that could see it — `link_check` stripped the fragment by design and exited 0 on that
exact input. Measured cost on a 41-page site: ~1.5 s, about +23% on a 6.8 s gate.]

[DECISION: **`precommit`, because `check` must not mutate** — the user's call, 2026-09-04, _"check
shouldn't mutate"_ and then _"i agree with docs build in precommit"_. `check` is the read-only,
CI-style half by construction: safe run concurrently, safe on a read-only checkout, and twice with
the same answer. Building a site into the working tree from a task documented as "no changes
written" is a category error whatever `.gitignore` thinks of the output. Zensical cannot avoid the
write either, probed at 0.0.44 rather than assumed: `zensical build` takes only `--config-file`,
`--clean` and `--strict`, with no output directory at all, and an out-of-tree `site_dir` in an
alternate config passes validation and then panics. So the achievable property is "leaves no net
change", never "writes nothing". The separate validate-mode the community ships — Zola's
`zola check`, Sphinx's `-b dummy`, Hugo's `--renderToMemory` — has no zensical equivalent.]

[PITFALL: the argument this beat is stronger than it looks and will be re-derived. Only `check` runs
in CI, so `check` is the cheap way to make a docs failure fail the run people already watch — and a
consumer with a docs site and no docs CI job of its own now needs one, which is a real cost this
placement imposes and the other did not. `power-user-linux-setup` paid it, giving `ci.yml` its own
`docs` job on push and pull_request. The trade was taken because a gate half that quietly stopped
being read-only is worse for every consumer, including the majority that have no docs site and gain
nothing from the build either way.]

[PITFALL: this landed in `check` first, on 2026-09-04, and was moved the same day. The plan that
specified `check` was filed from the consumer repo, revised **there** hours before the
implementation, and nothing carries a correction to a filed plan that has already been absorbed — so
the implementation was faithful to an artefact that had been withdrawn. Worth knowing as a property
of the filing mechanism rather than as a one-off: a filed plan is a snapshot, and the repo that
filed it can move on without the copy knowing.]

[PITFALL: **the anchor case is now covered twice, and that is not redundancy to tidy up.**
`link_check` gained anchor resolution later the same day, so the deploy failure above would today be
caught by either. They cover different surfaces: this one sees only a repo that has a docs site and
only the pages inside it, while `link_check` sees every tracked markdown file. Removing either
leaves a real gap — dropping this loses nav entries and everything else the renderer checks;
dropping the anchor half of `link_check` leaves `plans/` and `contributing/` cross-references
unchecked in every consumer, most of which have no docs site at all.]

[DECISION: in `check`, not in `precommit`. `precommit` is `pre=[fix, check]`, so `check` reaches
both — and only `check` reaches CI, which is what turns a Pages failure into a failure of the run
people already watch.]

[DECISION: the no-op is keyed on `mkdocs.yml`, not on whether zensical is installed. Keying on the
tool would make "this consumer's docs group is not synced" indistinguishable from "this repo has no
docs site", which is the silent pass the whole step exists to remove. Most consumers have no docs
site at all and none of them declares zensical on repo-tasks' behalf, so the config file is what
makes the step safe to run unconditionally.]

[PITFALL: this one step does **not** use `configs.require_tool`, and that is deliberate rather than
an oversight to tidy up. That helper's message names the `repo-tasks-quality` manifest and
`dependency-groups.dev`, which is right for every other gate binary and wrong for this one —
zensical is in the consumer's own `docs` group, so a consumer following that remediation would sync
the wrong group and see nothing change. `docs.py` carries its own preflight naming
`uv sync --group docs`.]

This is also the one step that makes "no changes written" not literally true: a repo with an
`mkdocs.yml` gets `site/` rebuilt. `site/` is gitignored in every consumer and `build` cleans on
entry rather than on exit, so nothing tracked moves and nothing accumulates between runs.

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
advisory blocks work. One did, for four days: `devpi-server`'s `setuptools<=81` held two advisories
open that nothing here could fix. The decision held, and the fix was to remove the dependency rather
than to suppress its advisory — see [`test-tiers.md`](test-tiers.md), "Package index". That is the
outcome the no-suppression rule is for: a suppression list would have hidden the pin instead of
costing it.]

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

### Nothing here runs on a schedule, and that is the decision

Three things answer a question whose answer changes without any code changing, so each is correctly
outside `check` — and each can therefore sit stale or red with a green terminal everywhere:
`deps.audit`, the integration tier (which sat red for an unknown length of time on a bad fixture,
and hid a second failure behind it while it was), and `ci.check-actions`.

[DECISION: no scheduled workflow. A schedule surfaces staleness only to a reader, and this repo
pushes straight to `main` and reviews no PRs — a red scheduled run has no natural audience. An
unwatched scheduled job is worse than a known gap, because it looks like coverage. The answer is
`ci.status` as a deliberate pre-push step, plus running the other two by hand when their subject
changes: `deps.audit` when dependencies move, `ci.check-actions` when a workflow is edited. The
residual staleness risk is accepted, not pending. Settled 2026-08-30.

This rules out a _schedule_, not a _trigger_. The push-triggered dependency audit is the trigger it
left open, and it landed 2026-08-31 — see "The dependency audit runs as its own workflow" below. The
gap that trigger cannot close, an advisory landing with no push here, is open on its own terms in
`plans/2026-09-04-scheduled-dependency-audit.md` rather than settled by this decision.]

**Run `inv ci.status` before pushing.** It is the habit the decision above rests on, and the only
thing standing between a failed push-triggered run and nobody noticing.

### The dependency audit runs as its own workflow

`security.yml` runs the audit on push to `main` and on manual dispatch; `security-reusable.yml`
holds the actual job and every other repo in the family calls it.

[DECISION: a separate workflow, not a step in `ci.yml`. The separation is the signal, not tidiness:
GitHub gives every workflow its own check run, its own name against the commit, and its own badge,
so `CI ✓` beside `Security ✗` says "the code is fine, the dependencies are not" with nothing further
to configure. Folding it into `ci.yml` would also put a network call inside the workflow whose whole
point is that `quality.check` runs offline, and would run it on every feature-branch push.]

[DECISION: **a red `main` on an unfixable advisory is the intended outcome**, per the user
2026-08-31. There is no suppression list and no acknowledge-and-move-on, so an advisory on a
transitive with no fixed version keeps `main` red until someone acts. This repo has been in that
exact state before — `devpi-server` pinned `setuptools<=81` for four days. Accepted, because the
alternative is a suppression file that outlives the advisory it silenced.]

[DECISION: SARIF uploaded to code scanning, so findings land in the Security tab, was **rejected on
uniformity**. It needs a GitHub Code Security licence on private repositories, and this family is
mixed — five public repos and four private ones, measured 2026-08-31 — so it could not be the same
everywhere, which was the requirement. `uv audit` also emits only `text` and `json`, so that route
would additionally need a SARIF converter nobody maintains. A separate workflow gets the same
"security is separate from correctness" reading for free, on every plan.]

[DECISION: the reusable workflow lives in **this** repo because this repo is public. On Free, Pro
and Team a reusable workflow must be in the same repository or a public one, so a public host is
callable from the family's private repos while a private host would need Enterprise.]

[DECISION: **callers pin a full SHA, not `@main`** — chosen by the user 2026-09-04 on stability. A
moving ref means every consumer's audit changes the moment this repo's `main` does, including in
repos nobody is working in; a SHA means a consumer runs the workflow it was pinned to until someone
changes it deliberately. The cost is the bump, and it is smaller than it looks: `ci.check-actions`
already parses a job-level `uses:` for a reusable workflow, recognises a 40-hex SHA, and reads a
trailing `# <version>` comment as the human-readable pin, so a stale ref is reportable rather than
invisible.]

[PITFALL: that currency check does not actually work for this pin **yet**. `_latest_tag` asks
`gh api repos/<owner>/<repo>/releases/latest`, which answers with GitHub Releases, not tags — and
this repo has a `v0.2.0` tag and no Release, so the reusable workflow's own ref resolves to
"nobody's release to track" and is skipped rather than reported. Until `inv release.create` has
published one, a pinned consumer goes stale silently and the bump is a thing someone has to
remember. That is the real cost of pinning here, and it is paid for stability deliberately.]

[PITFALL: the job installs nothing and caches nothing, and that is not an oversight to "fix" later.
`uv audit --locked` reads `uv.lock` and queries OSV — measured 2026-08-31 on a clean checkout with
no `.venv` at all, 0.72s wall. Adding `./bootstrap.sh` to give it `inv deps.audit` would install the
whole dev group to shell out to one uv subcommand, and would restrict the workflow to repos that use
`repo-tasks`. The cost of the raw command is that the string lives in two places;
`test_deps.py::test_audit_command_matches_the_reusable_workflow` fails if they diverge.]

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

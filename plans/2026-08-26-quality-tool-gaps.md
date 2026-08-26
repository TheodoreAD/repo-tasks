---
status: idea
updated: 2026-08-26
---

# Quality-gate coverage by concern: what the gate does not check

## Context

`inv quality.check` runs ruff (lint + format), dprint, basedpyright, shellcheck, shfmt, actionlint,
and the unit tier. Each of those picks is researched and settled —
[`contributing/type-checking.md`](../contributing/type-checking.md),
[`contributing/test-tiers.md`](../contributing/test-tiers.md), and
`power-user-linux-setup/plans/2026-08-14-python-repo-scaffolding.md` §C/§D carry the reasoning.

What has never been asked is the complementary question: **which classes of problem does the gate
not look for at all?** Prior research tuned the tools already chosen; this plan sweeps for concerns
with no tool behind them. Sorted by concern, one section each, so each can be decided on its own
merits instead of as one adopt-everything bundle.

Scope note: the gate ships to every consumer through `repo-tasks-quality`, so every addition here is
a dependency added to `power-user-linux-setup`, `scaffoldapy`, and every generated repo — see
[`contributing/consumer-sweep.md`](../contributing/consumer-sweep.md). The bar is correspondingly
higher than for a repo-local tool: a check that no-ops cleanly on a repo that doesn't have the
artifact kind (`shell_check`'s contract) is the shape that survives that.

[UNVERIFIED: every tool recommendation below is search-summary depth — package pages, project
READMEs, and 2026 blog/comparison posts, not CLI walkthroughs against this repo. `~/AGENTS.md`'s
"Choosing a tool or library" rule requires flagging that before any of these is treated as a
decision. `uv audit` is the one exception: verified live on this machine (uv 0.11.19,
`uv audit --help` works, OSV-backed, has `--locked` and `--output-format json`).]

## Open questions

### 1. Dependency vulnerabilities — nothing scans them today

`deps.py` locks, checks, lists, trees, and exports, but nothing ever asks whether a locked
dependency has a known CVE. uv shipped `uv audit` (0.10.12+, June 2026, OSV-backed); this machine is
on 0.11.19 and the command works. Zero new dependency, one new task, same tool the rest of the
module already wraps.

[NEEDS CLARIFICATION: does `deps.audit` belong in `quality.check`'s `pre=`, or is it a deliberate
standalone like `configs.pull`? A gate step whose result depends on an external database can fail on
a commit that changed nothing — the advisory landed, not the code. That is a real argument for
running it on a schedule (a cron workflow) rather than per-commit, and against calling it part of
"the gate is what CI runs".]

[NEEDS CLARIFICATION: `--locked` vs re-resolving, and what to do about a vulnerable _transitive_
dependency with no fixed version yet — does the task need a suppression mechanism, or is stopping
loudly correct until upstream moves?]

### 2. Lock drift is not gated locally

`inv deps.check` (`uv lock --check`) exists and is in no gate. CI covers the same ground only by
accident: `bootstrap.sh` runs `uv sync --locked`, which fails on drift. So a `pyproject.toml` edit
without a re-lock passes `inv quality.precommit` locally and fails in CI — the exact failure mode
`~/AGENTS.md`'s "the gate is what CI runs" rule exists to prevent.

[NEEDS CLARIFICATION: add `deps.check` to `quality.check`'s `pre=[...]` — is there a repo where the
lock legitimately lags (a consumer mid-bump)? If not this is a one-line fix.]

### 3. GitHub Actions security

actionlint covers correctness; `test.workflows` (act) covers execution. Neither looks at security,
and the workflow files here hold real privilege — `publish.yml` carries `id-token: write` for PyPI
Trusted Publishing.

- **zizmor** — static analysis for Actions specifically (template injection, over-broad tokens,
  artifact poisoning). Explicitly complementary to actionlint rather than overlapping. Ships on
  PyPI, so it joins `repo-tasks-quality` with no new mechanism, and file-gates the same way
  `workflow_check` already does.
- **Actions are not SHA-pinned** — `actions/checkout@v4` and `astral-sh/setup-uv@v9.0.0` are mutable
  refs. OpenSSF Scorecard's Pinned-Dependencies check wants full-length SHAs; the 2026
  TeamPCP/Miasma campaign is the live reason it stopped being theoretical.
- **`ci.yml` has no `permissions:` block** (inherits the repo default), no `concurrency` group, no
  `timeout-minutes`.
- **No `.github/dependabot.yml`** — nothing surfaces a moved action or dependency. SHA pinning makes
  this close to mandatory, since a pin goes stale silently.

[NEEDS CLARIFICATION: is zizmor a gate step (`quality.workflow-check` running both, like
`format_check` runs ruff and dprint) or its own task? Both are file-gated on
`.github/workflows/*.yml`, so folding it in costs nothing structurally.]

[NEEDS CLARIFICATION: SHA-pinning without dependabot means pins rot; with dependabot it means a
recurring PR stream on repos whose owner pushes straight to `main` and doesn't review PRs
(`~/AGENTS.md`'s personal-repo rule). Does the pin/update pair actually fit this family's workflow,
or is pinning just `publish.yml` — the one job holding a privileged token — the right scope?]

### 4. Container images are linted by nothing

Two Dockerfiles (`tests/fixtures/sample-service/Dockerfile`,
`tests/integration/clean-os.Dockerfile`) are formatted by dprint's dockerfile plugin and checked by
no linter. The integration tier builds both for real, which catches breakage but not badness —
unpinned base tags, root user, cache- defeating layer order.

`hadolint` is the standard pick, and it runs ShellCheck over `RUN` blocks, which pairs with what the
gate already does for `*.sh`. `docker build --check` (BuildKit, zero install) is the lighter
alternative but needs a daemon, which puts it in the integration tier rather than `check`.

[NEEDS CLARIFICATION: hadolint has no PyPI wrapper in the `shellcheck-py`/`shfmt-py` mould that this
family's "look for a maintained PyPI wrapper first" rule wants — it ships as a Haskell binary or a
container image. Does that rule out gate inclusion, or is a `hadolint-py`-shaped package real and
maintained? Unchecked.]

### 5. Test config strictness

`pytest.ini` has `-ra --strict-markers --strict-config` and stops there. Two settings that
consistently accompany those in flagship configs are missing:

- **`filterwarnings = error`** — every `DeprecationWarning` from invoke, uv, bump-my-version, and
  pytest itself currently passes silently. This family pins its whole toolchain to pre-1.0 surfaces
  (uv 0.11, ruff 0.16), where deprecation is the main early-warning channel.
- **`xfail_strict = true`** — an unexpected pass becomes a failure instead of being tolerated. There
  are no xfails today, so it costs nothing now and pre-empts a stale marker later.

[NEEDS CLARIFICATION: `filterwarnings = error` needs an escape hatch the moment a dependency starts
emitting a warning nobody here can fix. Per-warning `ignore` entries in `pytest.ini` are the
standard answer, but that file is shipped package data — a consumer-specific ignore has nowhere to
go except the unbuilt `configs.local.toml` mechanism (`2026-08-14-python-repo-scaffolding.md` §D).
Does this become that mechanism's first real live case?]

### 6. The unit tier's no-network promise is unenforced

[`contributing/test-tiers.md`](../contributing/test-tiers.md) says the unit tier needs "no Docker,
no network, nothing outside tmp_path". Two of those three are enforced structurally — `testpaths` as
an include not an exclude, and the autouse `tmp_cwd`/`isolated_home` fixtures. Network is enforced
by nothing: a unit test that reaches the wire passes here and fails on a firewalled runner.

`pytest-socket` (`--disable-socket --allow-unix-socket`) closes it the same way `isolated_home`
closed the stale-`~/.cache` leak — a structural guarantee rather than a rule someone remembers.

[NEEDS CLARIFICATION: does `--allow-unix-socket` cover everything the unit tier legitimately does?
`MockContext` never runs a subprocess, but pytest plugins and `importlib.resources` are unaudited
here.]

### 7. Coverage measurement is entirely absent

No `pytest-cov`, no coverage.py, no mention anywhere in the family. `--cov-fail-under` in CI is
ordinary practice elsewhere.

The honest caveat first: the unit tier is `MockContext` command-string assertion, so line coverage
would read high while proving little — `test-tiers.md` already documents two real `dist.py` bugs
that survived full unit coverage. The question coverage would actually answer, and nothing answers
today, is narrower: **which modules have no test file at all**, and which branches of a task module
are never entered.

[NEEDS CLARIFICATION: report-only (`inv test.coverage`, a number a human reads) or a `fail_under`
gate? A threshold on a mock-heavy suite mostly measures how much mocking was written, which is the
metric-gaming failure mode. Report-only has no teeth and gets ignored.]

[DEFERRED: a per-module "does a `tests/unit/test_<module>.py` exist" check is a cheaper answer to
the same question than a coverage tool, and `test-tiers.md` already states that convention as a
rule. Worth considering as a small task before reaching for coverage.py at all.]

### 8. Ruff rule surface

The curated `select` is researched (`2026-08-14-python-repo-scaffolding.md` §C2/§C4). Families worth
re-examining against _this_ codebase's actual shape:

- **`PT` (flake8-pytest-style)** — the biggest omission. This repo is test-dense and fixture-heavy;
  PT covers fixture/parametrize/raises misuse. Ruff's own issue #8796 records that some PT rules are
  contested, so this is a select-then-triage adoption, not a blind one.
- **`FURB` (refurb)** — modernization past `UP`'s syntax-only scope. Low noise.
- **`PGH`** — blanket-suppression hygiene, the ruff-side counterpart to
  `reportIgnoreCommentWithoutRule`.
- **`ERA`** — commented-out code. High false-positive risk against this family's heavy prose-comment
  style; trial before adopting.
- **`S` (bandit)** — the config comment rejects the family as noise, correctly for the whole family.
  `S602`/`S603`/`S607` (shell=True, partial executable paths) are the non-noise subset, and shelling
  out is what this package _is_. Per-rule, never per-family.

Correctly skipped, no change proposed: `T20` (printing is the product), `ARG`, `FBT`, `N`.

[NEEDS CLARIFICATION: `PT` on the tests tier only, or repo-wide? `per-file-ignores` is the
mechanism, but this family's config files have deliberately stayed free of per-repo-varying fields.]

### 9. Shipped types are a public API nothing tests

`src/repo_tasks/py.typed` plus `invoke-stubs` make this package's types part of its contract, and
`contributing/type-checking.md` documents how much work went into them. No test asserts them:
basedpyright checks that the source is internally consistent, not that a _consumer_ sees the
intended signature.

[NEEDS CLARIFICATION: `basedpyright --verifytypes repo_tasks` (a completeness report) or a small
`assert_type` test module? The latter would have caught the `@task`-erases-the-signature gap that
`invoke-stubs` exists to fix, which is the argument for it.]

### 10. Docs: link rot and spelling

`contributing/` and `plans/` are a large, densely cross-linked corpus, and plan retirement — a
routine operation with its own documented procedure — deletes files other files link to. The
procedure's step 5 says the finishing grep should return no live pointers; nothing enforces it.

- **`lychee`** checks relative and external links. The relative half is the valuable one here.
- **Spelling** (`typos`, or `codespell`'s misspelling-dictionary approach) is a nice-to-have on a
  corpus this prose-heavy.

[NEEDS CLARIFICATION: external link checking is a network call in the gate, which breaks the "unit
tier runs anywhere" property if it lands in `check`. Relative-links-only is offline and cheap — does
lychee support that split cleanly, and is the external half worth a separate scheduled job?]

### 11. Dependency hygiene beyond vulnerabilities

`deptry` finds unused, missing, and transitive dependencies, and reads uv projects natively. The
specific value here: `repo-tasks-quality` is _exported public API_ spliced into every consumer's dev
group by `configs.ensure_deps`, so an entry going stale ships silently to all of them.

[NEEDS CLARIFICATION: does deptry understand a dependency group that exists to be re-exported rather
than imported? Every tool in `repo-tasks-quality` is invoked as a subprocess and imported by nothing
— the textbook shape of a false "unused dependency" report.]

### 12. Secrets

Nothing scans for them. Risk here is genuinely low — no secrets in tree, Trusted Publishing means no
PyPI token exists to leak, GHCR uses the ambient `GITHUB_TOKEN`.

[NEEDS CLARIFICATION: is GitHub push protection already enabled on these repos? If so that is
probably the whole answer, and gitleaks in the gate is redundant weight shipped to every consumer.]

### 13. CI shape

- **No Python matrix.** `requires-python = ">=3.11"` is a claim about four interpreters; CI tests
  one, whichever uv picks (no `.python-version` in the repo). Either test the range or narrow the
  claim.
- **No uv cache** in the workflows (`astral-sh/setup-uv` has `enable-cache`).

[NEEDS CLARIFICATION: is `>=3.11` a real support claim, or just a floor nobody meant as a promise?
The answer decides whether this is a matrix to add or a `requires-python` to raise.]

### 14. Settled, no change proposed

Recorded so a later sweep doesn't re-litigate them:

- **`pre-commit`** — rejected in §C3 of `2026-08-14-python-repo-scaffolding.md` (a second runner,
  config format, and mental model beside invoke, which already aggregates tools behind one command).
  `~/AGENTS.md`'s rule against mechanisms that fire behind an agent's back reinforces it. Still
  right.
- **Linting for the non-Python languages dprint formats** — YAML's two real surfaces here are
  workflows (actionlint) and Helm charts (`helm lint`), both already covered by purpose-built tools.
  A general `yamllint`/`taplo lint` would add noise, not coverage.
- **License compliance** — personal repos, permissive throughout. Revisit only if a consumer goes
  corporate.
- **`configs.diff` in the gate** — read-only, so it dodges the silent-mutation objection that keeps
  `configs.pull` standalone, but `repo-tasks`' own root config files are _deliberately allowed_ to
  lead the packaged copies (§D, self-hosting). A gate step would fire on exactly the state the
  design calls normal.

## Recommended direction

Rough ordering, not a build order — each section above is independently decidable.

1. **`uv audit`** (§1) — an entire uncovered concern closed with a tool already installed and no new
   dependency for any consumer. Highest value-to-cost ratio on the page.
2. **`pytest.ini`: `filterwarnings = error` + `xfail_strict = true`** (§5) — two lines, and the
   first is a live early-warning channel currently muted.
3. **Workflow hardening** (§3) — `permissions:` and `concurrency` on `ci.yml` cost nothing;
   SHA-pinning `publish.yml` protects the one job holding a privileged token. zizmor is the larger
   decision and can follow.
4. **`deps.check` into `quality.check`'s `pre=`** (§2) — one line, closes a real local/CI
   divergence.
5. **ruff `PT`** (§8) and **pytest-socket** (§6) — both small, both fitting patterns this repo
   already argues for.
6. Everything else (§4, §7, §9–§13) needs its open question answered first.

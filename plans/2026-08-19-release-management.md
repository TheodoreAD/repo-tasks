---
status: landed
updated: 2026-08-19
---

## Context

Goal: gitflow branch flows (feature/release/hotfix start & finish) and semver version bumping, as
reproducible `inv` tasks matching this repo's existing `quality.py` philosophy — dedicated config,
every command echoed, no per-repo allowances, safe no-ops where an artifact kind is absent. Builds on
`plans/2026-08-19-monorepo-workspace-foundation.md` for project/group discovery.

Surveyed the mainstream python versioning/release tools before designing this:

- **python-semantic-release** — derives the bump from conventional-commit messages automatically.
  Has open, unresolved issues specifically about gitflow: a 4-branch gitflow repo's version
  determination breaks (python-semantic-release/python-semantic-release#789), and monorepo
  commit-scope filtering isn't supported (#1215). Automatic inference also fights gitflow's usual
  model, where a release manager _decides_ the bump at `release start` time rather than deriving it
  after the fact from history.
- **commitizen** — has explicit, documented monorepo guidance: component-scoped tag formats like
  `${version}-library-b`, one changelog/version per component. Still couples the bump decision to
  conventional-commit parsing by default.
- **bump-my-version** (successor to `bump2version`) — config-driven: reads current version out of
  whatever files you point it at, bumps the part you tell it to (`major`/`minor`/`patch`), writes it
  back, optionally commits and tags. No conventional-commit requirement, no inference — the caller
  states the bump explicitly. Closest fit to classic gitflow's human-decided release scope, and
  sidesteps python-semantic-release's gitflow branch-mapping problems by simply not depending on
  branch-name-driven inference at all. **Chosen.**
- No mainstream _python_ library does gitflow branch orchestration itself — that's traditionally
  nvie's `git-flow` / `git-flow-avh`, an external shell tool. Depending on it would add a system
  binary this repo doesn't otherwise require (today's dependency set is `git`, `ruff`,
  `basedpyright`, `dprint`, `shfmt` — all already assumed on `PATH`). **Reimplementing the branch
  mechanics directly with raw `git` commands avoids that new dependency.**

**Hands-on comparison (resolves the earlier "further research requested" flag):** all three tools
were actually installed and driven against a throwaway git repo simulating the docker+helm
group-bump scenario (a `pyproject.toml` `[project].version` plus a paired `chart/Chart.yaml`'s
`version`/`appVersion`).

- `bump-my-version` and `commitizen` **both** fully satisfy every hard requirement (explicit bump,
  multi-file group bump in one commit+tag, configurable tag template, independent-group isolation)
  — this was a close call, not a blowout. `bump-my-version` still wins on fit: it has no
  commit-message-inference code path at all (structurally impossible to regress into a "surprise
  inferred bump," the exact failure mode this plan's explicit-bump-only design existed to avoid),
  and its own dependency footprint (9 packages: click, httpx2, pydantic, pydantic-settings,
  questionary, rich, rich-click, tomlkit, wcmatch) doesn't drag in commitizen's
  changelog/conventional-commit machinery (this plan explicitly defers CHANGELOG generation).
  commitizen is a legitimate fallback if changelog generation is ever added later — its default
  substring-replace bumped both `Chart.yaml` keys with zero per-file regex, genuinely simpler there
  than bump-my-version's exact search/replace.
- **Real config-shape finding that changes Design §1 below:** bump-my-version's pure-CLI-only mode
  (`--no-configured-files` + positional file args + one global `--search`/`--replace`) cannot express
  different search/replace templates per file in one call — confirmed by hitting `Did not find
  'version = "0.2.0"' in file: 'chart/Chart.yaml'` when a TOML-style pattern was applied to the YAML
  file. A static, hand-authored `.bumpversion.toml` doesn't work either, since a group's file set
  (which projects/charts belong to it) isn't fixed — it's whatever `projects.py`/`repo-tasks.toml`
  resolve for that group at call time. **`version.py` must generate a temporary per-group
  `.bumpversion.toml` at runtime** (via `--config-file <tmp path>`), built from that call's resolved
  group members, not maintain a static config file.
- `python-semantic-release`: the plan's "derives the bump automatically" phrasing is slightly
  imprecise — real explicit-override flags exist (`--major`/`--minor`/`--patch`). But hands-on
  testing found two concrete blockers rather than just "fights gitflow's model" in the abstract: (1)
  `semantic-release version --minor --no-push --no-vcs-release` fails outright with `error: No such
  remote 'origin'` on a repo with no configured remote — directly conflicts with this plan's
  local-only-by-default `release_finish`/`hotfix_finish`; (2) `--minor` on a fresh repo with no prior
  release tag silently no-ops — prints `The next version is: 0.1.0!` (unchanged) and tags `v0.1.0`
  with no actual bump and no commit; only a second run, after a prior tag existed, bumped correctly.
  The explicit-override flags force the bump _type_ but don't bypass its release-history/commit-
  parsing engine, and the very first release is a silent-no-op trap. Confirms the plan's original
  instinct, on firmer ground than the initial search-summary survey had.

Decisions from review:

- Main branch: `main`.
- `release_finish`/`hotfix_finish` default to local-only (merge + tag, no push); an explicit `--push`
  flag opts into pushing branches and the tag to the remote in the same command.
- CHANGELOG generation is deferred — not in this plan's v1.
- Feature/release/hotfix/support gitflow is what's being built (Design §2 below). `support/*`
  landed after all — needed for real work sooner than expected; scoping it out originally undersold
  how small it actually is. Correction on attribution while implementing it: `support` branches
  aren't in nvie's original article at all (confirmed by re-reading it directly — the article only
  documents feature/release/hotfix) — they're a feature of his companion `git-flow` CLI tool
  specifically (its README: `git flow support start <release> <base>`, "the `<base>` arg must be a
  commit on `master`"), which is itself thin on the semantics beyond that. `version.py`'s bump logic
  stays independent of `gitflow.py`'s branch orchestration regardless, leaving a seam for a future
  trunk-based release module to reuse just the bump step without adopting gitflow's full branch
  model.
- Version scope follows `monorepo-workspace-foundation.md`'s grouped/hybrid model: `version.py`
  bumps and tags one _group_ at a time, not always a single project and not always the whole repo.

## Design

### 1. `src/repo_tasks/version.py` — `bump-my-version` wrapper

- New dev dependency: `bump-my-version`.
- `inv version.bump --part=major|minor|patch [--group=name]` — resolves every
  `projects.py`/`repo-tasks.toml` entry sharing `group` (default: Phase 1's sole implicit project),
  writes a **temporary per-group `.bumpversion.toml`** from those resolved entries (one
  `[[tool.bumpversion.files]]` block per file: a python project's `pyproject.toml` `[project].version`,
  and/or a paired Helm chart's `Chart.yaml` `version`/`appVersion` per
  `plans/2026-08-19-helm-chart-tasks.md`), invokes `bump-my-version bump <part> --config-file <tmp>`,
  then deletes the temp file. No static, hand-authored `.bumpversion.toml` — confirmed hands-on that
  bump-my-version's config-free CLI mode can't express per-file search/replace templates, and a
  group's file set isn't fixed ahead of time anyway. Tag name is set inside the generated config
  (`tag_name`), not a separate CLI flag:
  - `vX.Y.Z` when the group is Phase 1's sole implicit project.
  - `<group>-vX.Y.Z` once multiple groups exist (Phase 2), matching commitizen's documented
    monorepo tag-format precedent (also hands-on confirmed working via bump-my-version's own
    `tag_name` templating, not just commitizen's).
- Individually invocable outside a release flow — e.g. a plain point release with no gitflow
  ceremony at all. Returns the new version string.
- `tag=True` keyword arg (default on for standalone use). `gitflow.py`'s `release_start`/
  `hotfix_start` call `version.bump(..., tag=False)` — the tag belongs on `main` at _finish_ time
  per Design §2 below, not on `develop`/`main` at _bump_ time, so bump-my-version's own `tag=true`
  config line is conditional on this flag rather than always on.
- `current_version(c, group=None)` and `next_version(current, part)` — two small additions on top
  of the original design, needed once `gitflow.py`'s branch-then-bump order (Design §2) was
  corrected to match nvie's actual sequence: the release/hotfix branch has to be _named_ before the
  real, writing `bump` call runs on it. `next_version` is plain arithmetic (no subprocess) rather
  than shelling out to `bump-my-version show --increment` — safe to hand-roll because the config
  `bump`/`_bumpversion_config` always generates uses bump-my-version's untouched default
  parse/serialize (`major.minor.patch`), so there's no scheme this could diverge from. The actual
  file-writing/committing stays 100% owned by bump-my-version either way.

### 2. `src/repo_tasks/gitflow.py` — raw git plumbing

No external `git-flow` binary dependency; every step is a plain `c.run("git ...", echo=True)`,
mirroring nvie's git-flow branch-naming and merge-back conventions:

- `feature/*` branches off `develop`, merges back to `develop` only.
- `release/*` branches off `develop`; `hotfix/*` branches off `main`. Both finish by merging back to
  **both** `develop` and `main`, with the release tag created on `main`.

**Branch-then-bump order, straight from nvie's source article** (corrected after review — the
original design here had it backwards): the release/hotfix branch is cut _first_, unbumped, off its
base; the version bump commit is made **on the branch itself**, after it exists. Not
bump-the-base-then-branch — that would make an aborted release leave a stray bump commit sitting on
`develop`/`main` even with no release branch to show for it. `version.py`'s `next_version(current,
part)` computes the branch's name (pure arithmetic — the config our `bump` always generates never
customizes bump-my-version's parse/serialize, so hand-rolling this one piece doesn't risk diverging
from what the tool would compute) _before_ the real, file-writing `bump` call runs on the new
branch. `release_start(c, bump, group=None)` / `hotfix_start(c, bump, group=None)` do this — unaffected
by which finish mode (below) is used, since branch creation never touches a protected branch.

#### PR mode (default) vs. local mode — a scope decision from review

A protected `main`/`develop` (required reviews/CI) rejects a direct push outright, merge or no
merge — real for any team repo using the full gitflow convention. A single-person repo or one doing
trunk-based development with feature branches merged straight into `main` has nothing to protect
against and gains nothing from the ceremony. Decision: **PR mode, via the `gh` CLI, is the default
and primary path** for every `*_finish` task; **local mode (`local=True`) keeps the old
direct-merge-and-push behavior**, for a single-person repo or fast local testing with no `gh`, no
network, no waiting on a human reviewer. GitHub only — no GitLab/Merge Requests investment (see
`plans/2026-08-19-gitflow-protected-branches.md`, now superseded/absorbed into this section, for the
scope reasoning).

**Local mode** (`local=True`) is exactly what was designed and verified in dry-run round 2 below,
unchanged: `feature_finish(c, name, local=True)` merges directly into `develop`;
`release_finish`/`hotfix_finish(c, push=False, local=True)` merge into `main` (tag there), then into
`develop` — or, per nvie (quoting the article directly: _"when a release branch currently exists,
the hotfix changes need to be merged into that release branch, instead of develop"_), into an open
`release/*` branch instead if one exists for a hotfix (`git for-each-ref
refs/heads/release/*`, raises if more than one is open — ambiguous, this repo's model assumes at
most one release in flight at a time). `push=True` additionally pushes branches + tag. **Known,
accepted rough edge**, confirmed hands-on: a hotfix redirected into an in-flight release branch can
produce a real git merge conflict if both bumped the same version line — expected, not
auto-resolved (`git merge --no-ff` just fails, no `warn=True` anywhere in this file), resolved
exactly as a human running real `git-flow` would (normally keeping the release branch's own, higher
version), then the remaining steps (branch deletion, etc.) finished by hand — no "resume this task"
mechanism.

**PR mode** (default) can't complete synchronously — a real PR needs human review/CI before it
merges — so it's two steps per branch instead of one:

- `feature_finish(c, name)` — pushes `feature/<name>`, opens a PR against `develop`, stops. Nothing
  else to run once it's merged (a feature has no version/tag to finalize).
- `release_finish(c, push=False)` / `hotfix_finish(c, push=False)` — pushes the branch, opens a PR
  against `main`, stops. **No tag yet, no develop merge yet** — those can't happen until the PR
  actually merges (`push` is accepted but only meaningful for `local=True`; PR mode always pushes,
  that's what makes the PR possible).
- `release_finalize(c)` / `hotfix_finalize(c)` — run once a human has merged that PR on GitHub, from
  the same `release/*`/`hotfix/*` branch. `git fetch origin main` → `git checkout main` → `git merge
  --ff-only origin/main` (fails loudly if history unexpectedly diverged — no silent overwrite) →
  tags `main`'s now-updated tip → pushes the tag → branches a `sync/<tag>` branch off that same
  updated `main` → opens a **second** PR: `develop`, or (hotfix, same nvie redirect rule as local
  mode, checked again independently here) an open `release/*` branch. A fresh `sync/<tag>` branch
  rather than reusing the original `release/*`/`hotfix/*` branch: many GitHub repos auto-delete a
  branch the moment its first PR merges, which would silently break opening the second PR if it
  tried to reuse that same branch.

**General rule established here, meant to extend beyond this file**: any command that stops short of
"the whole flow is fully done" — because a PR was opened and needs a human, or because a guard
clause tripped — prints exactly what to run next (a private `_next_steps(*lines)` helper), rather
than leaving the caller to go read source to figure out what happens now. Applied throughout this
file: every `*_start`/`*_finish`/`*_finalize` in PR mode, and worth applying to any future task
elsewhere in this package with the same "stops for an external reason" shape.

**Known limitation, not yet verified:** the actual `gh pr create` call itself needs a real
GitHub-linked repo to exercise — the dry run below verified every git-only step (push, fetch,
ff-only merge, tag, tag push, sync-branch push) against a local bare repo standing in for `origin`,
confirmed the exact `gh pr create` command construction is reached with correct arguments, but
stopped there (`none of the git remotes configured for this repository point to a known GitHub
host`) rather than opening a real repo/PR under an account without asking first.

#### `support/*` branches

`support_start(c, version, base)` — `git checkout -b support/<version> <base>`, that's the entire
task, matching nvie's own `git-flow` tool's scope for this exactly: **start only, no
finish/merge-back**, because a support branch is a long-lived, permanently diverging maintenance
line for an old release (`base` is normally an old tag, e.g. `v1.4.0`), not a short-lived branch
that reconverges with `develop`/`main` — merging it back would pull old-line code forward into new
development. Prints the same "here's what to do next" guidance as every other stopping point in this
file. No PR-mode distinction for `support_start` itself — branch creation never touches a protected
branch, same as `release_start`/`hotfix_start`.

**Correction from review, before this ever shipped:** the original design said patching a support
branch afterward needed "no new machinery" — just `version.bump` plus a plain `git tag`/`git push`
directly on the branch. Wrong: **`support/*` produces artifacts that ship to prod, exactly like
`main`, so it needs to be protected exactly like `main`** — a direct push/commit doesn't work any
more than it would against a protected `main`. `support_hotfix_start(c, support, bump, group=None)` /
`support_hotfix_finish(c, support, push=False, local=False)` / `support_hotfix_finalize(c, support)`
give it the same PR-mode-primary, two-step shape as a regular hotfix (branch off `support/<support>`
unbumped → bump on the branch → PR into `support/<support>` → once merged, fetch+tag), reusing
`_open_pr`/`_next_steps`. Two real differences from a regular hotfix, both because a support line is
already permanently diverged from the mainline: **no `develop` merge at all**, and **no
release-branch redirect check** — that redirect exists to keep an active mainline release in sync,
which has nothing to do with an isolated support line. Branch naming: `support-hotfix/<support>/
<version>` — the `<support>` segment matters because `support_hotfix_finish`/`_finalize` need to
know which support branch a patch branch belongs to without depending on any persisted state (this
tool is stateless throughout), and `<support>` is passed again explicitly at finish/finalize time,
same "no hidden state" posture as everything else here.

### 3. Explicit bump type only

`major`/`minor`/`patch` is always an explicit argument to `release_start`/`hotfix_start`, never
inferred from commit history. Deliberate: this is what avoids python-semantic-release's gitflow
branch-mapping issues entirely, by not depending on automatic inference in the first place.

## Files touched

- `src/repo_tasks/version.py` (new) — no static `.bumpversion.toml`; generated at runtime per bump.
- `src/repo_tasks/gitflow.py` (new) — PR mode (default, via the `gh` CLI) and local mode
  (`local=True`), per the "PR mode vs. local mode" subsection above.
- `pyproject.toml` — add `bump-my-version` to `dependency-groups.dev`. `gh` itself is not a python
  dependency — assumed already on `PATH`, same posture as `git`/`ruff`/`basedpyright`/`dprint`/
  `shfmt` elsewhere in this repo, only needed at all when PR mode's `*_finish`/`*_finalize` tasks
  actually run.
- `src/repo_tasks/__init__.py` — nest the new `version`/`gitflow` collections into `ns` alongside the
  existing `quality` one (consumers pick both up automatically via `from repo_tasks import ns`, no
  `tasks.py` change needed)

## Verification

- Unit tests mocking `c.run` for `gitflow.py`'s branch/merge/tag commands and `version.py`'s
  bump-my-version invocation, following `tests/test_quality.py`'s existing `MockContext`/`Result`
  pattern.
- Manual dry run against this repo itself on a throwaway branch: `feature_start` → `feature_finish`,
  then `release_start --bump=patch` → `release_finish` (no `--push`), inspecting `git log`/`git tag`
  before trusting the flow more broadly.

**Dry run result (round 1):** run in an isolated scratch repo (editable-installed from this repo's
real source) rather than against this repo's own branches, since Phase 1 work was still uncommitted
at the time. Caught a real bug the unit tests missed: `_start` was bumping the version on whatever
branch happened to be checked out _before_ switching to `develop`/`main`, so the release/hotfix
branch got cut from an unbumped base and the bump commit landed on the wrong branch. Fixed by
checking out the base branch before bumping, not after; added a regression test asserting full
call _order_ (`tests/test_gitflow.py`'s prior assertions only checked the tail of the call list,
which is why they didn't catch it). Re-run confirmed: `main` ends at the bumped version, the tag
lands on the right commit, `develop` stays in sync, no stray branches survive.

**Dry run result (round 2, after the nvie-alignment corrections above):** re-verified branch-then-
bump ordering directly (`develop`'s/`main`'s version file confirmed untouched right after
`release_start`/`hotfix_start` — only the new branch has the bump). Then exercised the hotfix
redirect specifically: opened `release/1.1.0` off `develop` (left unfinished), cut and finished
`hotfix/1.0.1` off `main` — confirmed the merge-back targeted `release/1.1.0`, not `develop`
(`develop` stayed at the old version throughout). Hit the expected version-line merge conflict doing
so (matches the "known, accepted rough edge" noted above); resolved it by hand keeping the release
branch's version, then finished the release — confirmed `main` and `develop` both converge on
`1.1.0`, both tags (`v1.0.1`, `v1.1.0`) land on the correct commits. Also caught and fixed an
unrelated real bug in the same pass: `_open_release_branch`'s `git for-each-ref
--format=%(refname:short)` wasn't shell-quoted, so the bare parentheses broke the shell `c.run`
invokes through — fixed by single-quoting the format string.

**Dry run result (round 3, PR mode):** scratch repo with a local **bare** repo standing in for
`origin` (no real GitHub host). `release_start` → `release_finish` (PR mode, default) pushed
`release/1.1.0` to that bare "origin" correctly, then reached `gh pr create --base main --head
release/1.1.0 ...` with exactly the expected arguments before failing on `none of the git remotes
configured for this repository point to a known GitHub host` — the correct, expected boundary for a
non-GitHub remote. Simulated "the PR was merged" by pushing a merge commit directly to the bare
repo's `main` (standing in for what GitHub's merge button would produce), then ran
`release_finalize`: fetched that merged `main` correctly, fast-forwarded local `main` to it, tagged
`v1.1.0`, pushed the tag, branched and pushed `sync/v1.1.0`, then reached `gh pr create --base
develop --head sync/v1.1.0 ...` with correct arguments before hitting the same expected
no-GitHub-host boundary. Every git-only step in both the `*_finish`→PR and `*_finalize`→PR paths is
confirmed correct; the `gh pr create` calls themselves (and the hotfix-redirect variant of
`*_finalize`'s second PR) are covered by unit tests but not yet exercised against a real
GitHub-linked repo. Follow-up plan for that:
`plans/2026-08-19-gitflow-test-repo-twin.md` (permanent test-repo twin, not started yet).

`support_start` needed no separate dry run — it's a single `git checkout -b`, the exact same
primitive `feature_start`/`release_start`/`hotfix_start` already exercise for real in rounds 1 and 2
above, just with a caller-supplied `base` instead of a hardcoded `develop`/`main`.

**Dry run result (round 4, support_hotfix):** local mode verified in a scratch repo (tag `v1.4.0` →
`support_start` → `support_hotfix_start --bump=patch` → `support_hotfix_finish --local`) — confirmed
`support/1.4.x` ends up merged, tagged, and the patch branch deleted, with `develop` never entering
the picture at all. PR mode verified the same two-boundary pattern as round 3, against a local bare
repo standing in for `origin`: `support_hotfix_finish` reached `gh pr create --base support/1.4.x
--head support-hotfix/1.4.x/2.1.0 ...` with correct arguments before the expected no-GitHub-host
failure; after simulating the PR merge (pushing a merge commit directly to the bare repo, standing
in for GitHub's merge button), `support_hotfix_finalize` fetched, fast-forwarded, tagged
`v2.1.0` on `support/1.4.x`, and pushed the tag — confirmed no `gh pr create` call at all in that
run, matching the "no second PR" design.

## Known follow-up (2026-08-20)

Surfaced while designing `plans/2026-08-20-venv-deps-tasks.md`'s `venv.sync --locked`:
[astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643) — `uv sync --locked` (and
`--no-install-project`) fails if _only_ the project's own version changed in `pyproject.toml` with
no dependency change, because `uv.lock` embeds that version too. `version.bump` here writes the new
version via `bump-my-version` but never re-runs `uv lock`, so a bump commit leaves `uv.lock` stale
until something notices via a failed `--locked` sync. Not urgent today (the `venv`/`deps` split
that would surface this in practice hasn't landed yet), but `_bump` (or `bump`'s caller in
`gitflow.py`) should run `deps.lock` as part of the bump commit once that module exists, so the
commit that changes the version and the commit that re-locks never drift apart.

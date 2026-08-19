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
- Feature/release/hotfix gitflow is what's being built (Design §2 below); long-lived `support/*`
  branches (for patching an old major/minor line) are out of scope for v1 — genuinely separate
  machinery (branches off an old tag rather than `develop`/`main`), not a trivial variant of the
  other three, and no concrete need for it yet. `version.py`'s bump logic stays independent of
  `gitflow.py`'s branch orchestration either way, leaving a seam for a future trunk-based release
  module (or a later `support` addition) to reuse just the bump step without adopting gitflow's full
  branch model.
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
branch.

Tasks:

- `feature_start(c, name)` / `feature_finish(c, name)`
- `release_start(c, bump, group=None)` — checks out `develop`, branches `release/<next_version>` off
  it, then calls `version.bump(part=bump, group=group, tag=False)` **on the release branch**.
- `release_finish(c, push=False)` — merges the release branch into `main` and `develop`, tags `main`
  at the merge commit, deletes the release branch. Pushes branches + tag only if `push=True`. No
  `name`/branch argument on finish — reads the current branch (via `git rev-parse --abbrev-ref
  HEAD`), same convention the real `git-flow` tool uses; the tag itself is derived from the branch
  name (`release/<version>` → `v<version>`), not passed separately.
- `hotfix_start(c, bump, group=None)` / `hotfix_finish(c, push=False)` — same shape as release,
  sourced from `main` instead of `develop`.

**Hotfix merge-back exception, also straight from nvie's article** (quoting it directly: _"when a
release branch currently exists, the hotfix changes need to be merged into that release branch,
instead of develop"_): `hotfix_finish` checks `git for-each-ref refs/heads/release/*` after tagging
`main`, and if a `release/*` branch is open, merges into **that** instead of `develop` — `develop`
picks the fix up later, transitively, when the release itself finishes. Raises if more than one
`release/*` branch exists (ambiguous — this repo's model assumes at most one release in flight at a
time, same as nvie's). `--push` pushes whichever branch actually got the merge (`main
<merge_back_target>`), not a hardcoded `main develop`.

**Known, accepted rough edge:** if a hotfix bumps a version that collides with an in-flight release
branch's own already-bumped version line, merging into the release branch produces a real git merge
conflict on that line (both sides touched the same line differently) — confirmed hands-on in the
dry run below. This is correct, expected behavior, not something to auto-resolve: `git merge --no-ff`
just fails and the task halts (no `warn=True` anywhere in `gitflow.py`), same as any other `c.run`
failure. A human resolves it exactly as they would running the real `git-flow` tool by hand
(normally by keeping the release branch's own, higher version number) and finishes the remaining
steps (deleting the hotfix branch, etc.) manually — there's no "resume this task" mechanism.

### 3. Explicit bump type only

`major`/`minor`/`patch` is always an explicit argument to `release_start`/`hotfix_start`, never
inferred from commit history. Deliberate: this is what avoids python-semantic-release's gitflow
branch-mapping issues entirely, by not depending on automatic inference in the first place.

## Files touched

- `src/repo_tasks/version.py` (new) — no static `.bumpversion.toml`; generated at runtime per bump.
- `src/repo_tasks/gitflow.py` (new)
- `pyproject.toml` — add `bump-my-version` to `dependency-groups.dev`
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

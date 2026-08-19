---
status: planned
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

**Further research requested before implementation starts:** the survey above (drawn from web
search summaries, not hands-on trials) isn't considered deep enough yet to fully close out the
bump-my-version-vs-commitizen-vs-python-semantic-release choice. Before starting Design §1
(`version.py`), do a proper hands-on comparison — actual CLI walkthroughs of each tool's bump/tag
flow, real config file examples (`.bumpversion.toml` vs `.cz.toml`), and a closer look at
commitizen's monorepo tag-format mechanics specifically — rather than relying on the search-result
summary this plan currently cites.

Decisions from review:

- Main branch: `main`.
- `release_finish`/`hotfix_finish` default to local-only (merge + tag, no push); an explicit `--push`
  flag opts into pushing branches and the tag to the remote in the same command.
- CHANGELOG generation is deferred — not in this plan's v1.
- Full gitflow (feature/release/hotfix/support) is what's being built, but `version.py`'s bump logic
  stays independent of `gitflow.py`'s branch orchestration, leaving a seam for a future trunk-based
  release module to reuse just the bump step without adopting gitflow's branch model.
- Version scope follows `monorepo-workspace-foundation.md`'s grouped/hybrid model: `version.py`
  bumps and tags one _group_ at a time, not always a single project and not always the whole repo.

## Design

### 1. `src/repo_tasks/version.py` — `bump-my-version` wrapper

- New dev dependency: `bump-my-version`.
- `inv version.bump --part=major|minor|patch [--group=name]` — resolves every
  `projects.py`/`repo-tasks.toml` entry sharing `group` (default: Phase 1's sole implicit project),
  bumps the requested part, writes every file in that group (a python project's `pyproject.toml`
  `[project].version`, and/or a paired Helm chart's `Chart.yaml` `version`/`appVersion` per
  `plans/2026-08-19-helm-chart-tasks.md`), commits, and tags:
  - `vX.Y.Z` when the group is Phase 1's sole implicit project.
  - `<group>-vX.Y.Z` once multiple groups exist (Phase 2), matching commitizen's documented
    monorepo tag-format precedent.
- Individually invocable outside a release flow — e.g. a plain point release with no gitflow
  ceremony at all.
- Dedicated config file `.bumpversion.toml` (bump-my-version's own default name) rather than a
  `[tool.bumpversion]` table inside `pyproject.toml`, matching this repo's `ruff.toml`/
  `pyrightconfig.json`/`pytest.ini` per-tool-own-file precedent.

### 2. `src/repo_tasks/gitflow.py` — raw git plumbing

No external `git-flow` binary dependency; every step is a plain `c.run("git ...", echo=True)`,
mirroring nvie's git-flow branch-naming and merge-back conventions:

- `feature/*` branches off `develop`, merges back to `develop` only.
- `release/*` branches off `develop`; `hotfix/*` branches off `main`. Both finish by merging back to
  **both** `develop` and `main`, with the release tag created on `main`.

Tasks:

- `feature_start(c, name)` / `feature_finish(c, name)`
- `release_start(c, bump, group=None)` — calls `version.bump(part=bump, group=group)` first, then
  creates the `release/*` branch off the now-bumped `develop`.
- `release_finish(c, push=False)` — merges the release branch into `main` and `develop`, tags `main`
  at the merge commit, deletes the release branch. Pushes branches + tag only if `push=True`.
- `hotfix_start(c, bump, group=None)` / `hotfix_finish(c, push=False)` — same shape as release,
  sourced from `main` instead of `develop`.

### 3. Explicit bump type only

`major`/`minor`/`patch` is always an explicit argument to `release_start`/`hotfix_start`, never
inferred from commit history. Deliberate: this is what avoids python-semantic-release's gitflow
branch-mapping issues entirely, by not depending on automatic inference in the first place.

## Files touched

- `src/repo_tasks/version.py` (new)
- `src/repo_tasks/gitflow.py` (new)
- `.bumpversion.toml` (new, this repo's own — Phase 1 config bumping its own `pyproject.toml`)
- `pyproject.toml` — add `bump-my-version` to `dependency-groups.dev`
- `tasks.py` — wire the new `version`/`gitflow` collections alongside the existing `quality` one

## Verification

- Unit tests mocking `c.run` for `gitflow.py`'s branch/merge/tag commands and `version.py`'s
  bump-my-version invocation, following `tests/test_quality.py`'s existing `MockContext`/`Result`
  pattern.
- Manual dry run against this repo itself on a throwaway branch: `feature_start` → `feature_finish`,
  then `release_start --bump=patch` → `release_finish` (no `--push`), inspecting `git log`/`git tag`
  before trusting the flow more broadly.

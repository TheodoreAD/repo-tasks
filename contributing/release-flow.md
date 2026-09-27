# Release flow

How the two branching models are applied — `src/repo_tasks/gitflow.py` and
`src/repo_tasks/trunkflow.py` — what each flow does, why it is shaped that way, and where it can
leave you stuck. For what a version _number_ is and how it is written across python/docker/helm, see
[`versioning.md`](versioning.md).

## Two models ship, and a repo uses one

| model       | namespace     | for                                                      |
| ----------- | ------------- | -------------------------------------------------------- |
| gitflow     | `gitflow.*`   | a repo with `develop`, staged releases, PRs, an rc cycle |
| trunk-based | `trunkflow.*` | owner-direct-to-`main`, no release branch, no rc         |

They are alternatives, never both. Which one a repo uses follows from whether it has a `develop`
branch — this repo does not, so it uses `trunkflow`. The `-flow` suffix is the marker for the class;
see [`task-module-conventions.md`](task-module-conventions.md), "A shared suffix marks a family of
interchangeable modules".

[DECISION: a second namespace, not a mode flag on `gitflow.*`. The two are not near-duplicate trees
— gitflow is twelve tasks, trunkflow is one — so a `model = "..."` config key would leave ten task
names advertised in `inv --list` and inert in a repo with no `develop`, which is a least-surprise
failure. The existing PR-vs-local axis stays orthogonal to the model choice: a trunk repo can still
want a PR.]

### The trunk flow, end to end

```shell
inv trunkflow.cut --bump minor   # bump + tag, locally, nothing pushed
inv release.push-tag             # the release gate
inv release.create               # a GitHub Release, if one is wanted
```

Three commands rather than one, and the split is the design rather than an omission.

[DECISION: **`trunkflow.cut` pushes nothing by default.** Pushing the tag is what publishes across
this ecosystem — `requests`, `flask` and `httpx` all trigger their publish workflow on a tag push,
and PyPA's own guide tells you to push a tagged commit to publish. So a bump that pushed its own tag
would make publication a side effect of asking for a version number. `--push` opts back in for
someone who genuinely wants one command. Researched from those projects' own workflow files,
2026-09-04.]

[PITFALL: this repo proved the point on itself. `publish.yml` used to fire on `push: tags: v*` with
an **unconditional** TestPyPI job, so `inv trunkflow.cut` — as first written, pushing its own tag —
meant "upload to TestPyPI and queue a PyPI approval". The unit tests could not catch it, because
they mock every `c.run` and so know nothing about what a real push triggers. `publish.yml` is now
disabled at its trigger; see the header comment in that file for what re-enabling needs.]

**Re-check that before every tag push rather than remembering it.** The property that makes a tag
push cheap — no workflow in this repo triggers on tags — was once false here, and re-establishing it
costs one `rg` over `.github/workflows/`. That is the difference between a version number and a
publication, and it was confirmed again before pushing `v0.3.0` on 2026-09-08.

[PITFALL: **a `release:` line in a workflow is as likely to be a job name as a trigger, and they
mean opposite things.** `docker-release.yml` reads as though it fires on `release:`, which would
couple `inv release.create` to an image push; that `release:` is the job's name and the workflow is
`workflow_dispatch` only. A grep for `^  release:` finds both spellings at the same indent, so read
the block it belongs to rather than the line.]

[DECISION: both publication steps live in `release.py`, not in either flow, because neither is
specific to a branching model — gitflow tags `main` after a PR merges, trunkflow tags it directly,
and either tag is published identically. `release.push-tag` sends the branch first, then the tag, so
the tagged commit arrives under a ref rather than reachable only from a tag; it refuses a tag that
does not point at a commit on that branch, which is how a tag left on an abandoned branch would
otherwise ship as the release.]

### Which part to bump

Not SemVer's breaking-vs-non-breaking, which under `0.x` guarantees nothing anyway and would cost
judgement on every release. **Minor means the shipped surface moved; patch means it did not** — see
[`versioning.md`](versioning.md) for the enumerated surface. The question it answers is the one a
consumer actually has: whether they need to run `configs.pull` and read a diff, or can upgrade
without looking.

## Why raw git, not the `git-flow` binary

No mainstream python library does gitflow branch orchestration; the traditional answer is nvie's
`git-flow` / `git-flow-avh`, an external shell tool. Depending on it would add a system binary this
repo doesn't otherwise require — the assumed-on-`PATH` set is `git`, `ruff`, `basedpyright`,
`dprint`, `shfmt`, plus `gh` only when PR mode actually runs. Every step is therefore a plain
`c.run("git ...", echo=True)`, following nvie's branch-naming and merge-back conventions directly.

## The branch model

- `feature/*` branches off `develop` and merges back to `develop` only.
- `release/*` branches off `develop`; `hotfix/*` branches off `main`. Both finish by merging back
  into **both** `develop` and `main`, with the release tag created on `main`.
- `support/*` branches off an old tag and never reconverges.

### Branch first, then bump — the order matters

The release/hotfix branch is cut **first, unbumped**, off its base; the version bump commit is made
**on the branch itself**, after it exists. This is nvie's own order, and the reason is failure
behavior: bump-the-base-then-branch leaves a stray bump commit sitting on `develop`/`main` when a
release is abandoned, with no release branch to show for it.

That ordering is why `version.py` exposes `next_version(current, part)` as pure arithmetic — the
branch has to be _named_ before the real, file-writing `bump` runs on it. See
[`versioning.md`](versioning.md#why-next_version-is-hand-rolled) for why hand-rolling that one
computation is safe.

An earlier implementation had this backwards and bumped on whatever branch happened to be checked
out. The regression test that pins it asserts the full call _order_, not just the tail of the call
list — asserting the tail is precisely why the original tests missed the bug.

## PR mode (default) vs. local mode

A protected `main`/`develop` rejects a direct push outright, merge or no merge. A single-person repo
has nothing to protect against and gains nothing from the ceremony. Both are real, so both exist:

- **PR mode** (default, needs `gh`) — the primary path for every `*_finish`.
- **Local mode** (`local=True`) — direct merge and optional push. For a single-person repo, or fast
  local testing with no `gh`, no network, and no waiting on a reviewer.

GitHub only. No GitLab/Merge Requests support, deliberately.

### PR mode is two steps, because it has to be

A real PR needs human review before it merges, so `*_finish` cannot complete synchronously:

| task                                       | does                                                                                                          |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `feature_finish(name)`                     | push branch, open PR against `develop`, stop. Nothing further — a feature has no version or tag to finalize.  |
| `release_finish()` / `hotfix_finish()`     | drop the rc if there is one, push branch, open PR against `main`, stop. **No tag yet, no develop merge yet.** |
| `release_finalize()` / `hotfix_finalize()` | run _after_ a human merged that PR, from the same branch.                                                     |

`*_finalize` does: confirm the PR is `MERGED` (`gh pr view`, see "Known bad states") →
`git fetch origin main` → `git checkout main` → `git merge --ff-only origin/main` → tag the
now-updated tip → push the tag → branch `sync/<tag>` off that same updated `main` → open a
**second** PR into `develop` (or, for a hotfix, an open `release/*` — same redirect rule as local
mode, checked independently here).

The `--ff-only` is deliberate: it fails loudly if history diverged unexpectedly rather than silently
overwriting.

`push` is accepted by `*_finish` but only means anything for `local=True` — PR mode always pushes,
since that is what makes the PR possible.

### Why `sync/<tag>` instead of reusing the release branch

Many GitHub repos auto-delete a branch the moment its first PR merges. Reusing the original
`release/*`/`hotfix/*` branch for the second PR would break silently on exactly those repos, so
`*_finalize` cuts a fresh `sync/<tag>` branch off the updated `main`.

### Every stopping point prints what to run next

Any command that stops short of "the whole flow is done" — because a PR needs a human, or because a
guard clause tripped — prints the next command via a private `_next_steps(*lines)` helper, rather
than leaving the caller to read source. This is a general convention, not a gitflow-local one; see
[`task-module-conventions.md`](task-module-conventions.md#stop-loudly-and-say-what-to-run-next).

## The release-candidate cycle

A release is staged before it ships, and staging needs a real artifact with a real version. The
cycle lives on the release branch, nvie's canonical shape with one addition — a tag per candidate:

1. `release_start --bump minor` cuts `release/X.Y.0` and bumps to `X.Y.0rc1` (no tag). The branch is
   named after the _final_ version it will ship, from the start.
2. `release-candidate`, as many times as staging needs: bumps `rcN` → `rcN+1`, tags `vX.Y.0rcN+1`
   **on the release branch**, pushes branch and tag. The tag is what the tag-triggered workflows
   build from (`publish.yml` sends an rc to TestPyPI only, never the real index). The first
   candidate is `release_start`'s own rc1 — tag it by hand if it should be built, or cut rc2.
3. `release_finish` bumps to the final `X.Y.0` as its first step (one more commit on the branch),
   then proceeds as before. `main` receives the final version and `*_finalize` tags it `vX.Y.0`.

A hotfix goes straight to its final version by default — it ships as soon as it is reviewed — and
`hotfix_start --rc` opts into the same cycle; `release-candidate` accepts a `hotfix/*` branch for
that. A support patch never has a candidate. The rc tags stay on the branch's history, which after
the sync merge is reachable from `develop` too; `_require_tag_absent` checks each candidate's tag
before cutting it, the same guard as the final's.

A repo that does not want a release branch at all wants `trunkflow`, not a lighter gitflow — see
"Two models ship, and a repo uses one" above. A lighter gitflow (release straight from `develop`, or
rc tags cut on `develop`) was considered and not built.

## The hotfix redirect

Quoting nvie directly: _"when a release branch currently exists, the hotfix changes need to be
merged into that release branch, instead of develop."_ Both modes implement this —
`git for-each-ref
refs/heads/release/*`, and a raise if more than one release branch is open, since
that is ambiguous and this repo's model assumes at most one release in flight.

The `for-each-ref` format string must stay single-quoted (`'%(refname:short)'`). Unquoted, the bare
parentheses break the shell that `c.run` invokes through — a real bug found in a dry run.

## Known bad states and how to get out

### Version-line merge conflict during a hotfix redirect

**Expected, not a bug.** A hotfix redirected into an in-flight release branch conflicts when both
bumped the same version line. `git merge --no-ff` just fails — there is no `warn=True` anywhere in
`gitflow.py`, and nothing auto-resolves it.

Recover the way a human running real `git-flow` would: resolve the conflict keeping **the release
branch's own, higher version**, then finish the remaining steps (branch deletion and so on) by hand.
There is no "resume this task" mechanism — the task does not track where it stopped.

In PR mode the conflict shows up as a `sync/<tag>` PR into the release branch that GitHub cannot
merge. `hotfix_finalize` leaves you on the sync branch, so resolve it there:

```shell
git fetch origin release/<v>
git merge origin/release/<v>             # conflicts on the version line
git checkout --theirs pyproject.toml     # keep the release's version
git add pyproject.toml
git commit --no-edit
git push origin sync/<tag>
```

Do the same for every other file the bump wrote and git reports as conflicted: `uv.lock`, and each
`Chart.yaml` in the version group. The twin has neither, so only `pyproject.toml` is exercised. The
PR then merges cleanly, and the fix reaches develop when the release ships.
`test_hotfix_during_an_open_release_syncs_into_the_release_branch` drives exactly this sequence
against the twin.

### A hotfix's sync PR opened into a release that already shipped

This one comes from repo-tasks before 2026-09-28, not from your own actions. PR mode's `*_finalize`
left the finished `release/*` branch in the clone, and `hotfix_finalize` picked its sync PR's target
from local branches. So in a clone that had finished one release, the next hotfix's sync PR went
into that shipped release, and the fix never reached develop. Reproduced against the twin before the
fix: hotfix 0.8.1's sync PR opened into `release/0.8.0`.

Now `*_finalize` deletes the finished branch locally and on origin, and `hotfix_finalize` asks
origin which release is in flight.
`test_hotfix_after_a_finished_release_in_the_same_clone_syncs_into_develop` pins it. To recover a PR
opened by an older version, retarget it before merging, then clear what was left behind:

```shell
gh pr edit <number> --base develop
gh pr merge <number> --merge
git branch -D release/<shipped version>
git push origin --delete release/<shipped version>
```

The retarget was done on the twin to clean up the reproduction, and `develop` came out containing
the hotfix tag.

### A start refused because the base is behind origin

`release_start`, `hotfix_start` and `support_hotfix_start` fetch their base and refuse when the
local copy is behind origin's. Without the check, a clone that had not pulled cut its branch from an
old commit and nothing said so. Run the `git pull --ff-only origin <base>` the message names, then
re-run the task. Offline, or with no `origin`, the check is skipped, and a failed fetch says so.

### Abandoning a release or hotfix branch

The cheap one, by construction: branch-then-bump means `develop`/`main` never received anything.
Delete the branch (`git branch -D release/<v>`, plus `git push origin --delete release/<v>` and
closing its PR if `*_finish` already ran). The version number was never tagged, so it stays
available and the next `release_start` computes it again.

### `*_finalize` run before the PR merged

Refused by `_require_merged_pr`: `*_finalize` asks `gh pr view <branch> --json state` first and
stops unless it reports `MERGED`, before fetching or touching `main`. The task is guarded because
the failure was silent, not loud — `git merge --ff-only origin/main` succeeds trivially whenever
local and remote `main` already agree, so an early `_finalize` used to tag the _old_ tip and push
that tag, which is the next state below. The guard reads the PR's state rather than checking
ancestry because a squash or rebase merge leaves no ancestry for `git merge-base --is-ancestor` to
find; `gh` is already a PR-mode requirement, so it costs nothing new.

[PITFALL: this guard did not exist until 2026-08-25. On a repo where `*_finalize` ran early before
that, look for a tag pointing at a commit that is not the merge — `git log -1 <tag>` — and treat it
as the wrong-commit case.]

### A tag on the wrong commit

Moving a tag is only clean while nobody else has it. Locally: `git tag -d <tag>`,
`git push origin :refs/tags/<tag>`, re-tag the right commit, push again. Every clone that already
fetched keeps the old one — git does not update a tag that moved on the remote without
`--force`/`--prune-tags` — so on a shared repo tell people, or expect stale tags.

**If a tag-triggered publish already ran, the version is gone, not the tag.** `publish.yml` fires on
`v*`; a wrong tag that reached PyPI has burned that version number permanently (a PyPI release can
be deleted but its number can never be re-uploaded). The recovery there is not moving the tag but
shipping the next patch version with the right content, and leaving the wrong tag in place so the
history says what actually happened. GHCR image tags and OCI chart versions _can_ be overwritten,
but a consumer that already pulled by tag will not notice.

### `sync/<tag>` PR closed without merging

`main` is tagged and released; `develop` still carries the pre-release version. Nothing breaks
immediately — which is the problem: the next `release_start` computes its version from `develop`'s
stale number and lands on one `main` already shipped. `_require_tag_absent` catches that at start
time (`git tag --list v<next>` non-empty) and refuses before cutting a branch, naming the missing
sync PR. It reads the _local_ tag list: on the machine that ran `*_finalize` the tag is there; on
another clone it is there once that clone has fetched `main` since the release (git auto-follows
tags into fetched history), so a stale clone that skipped fetching can still get past it.

Recovery is re-creating what `*_finalize` did: `git checkout -b sync/<tag> <tag>`, push it, open a
PR into `develop` (or into the open `release/*` branch for a hotfix — the redirect rule applies to
the retry as much as to the original). There is no task for this on purpose: the merge itself is the
PR stage a team cannot automate, and the two git commands are the entire retry.

[DECISION: both guards read state that already exists (`gh`'s PR state, the local tag list) instead
of tracking flow progress in a file. The tool stays stateless — `<support>` is passed explicitly at
every step for the same reason — and a guard that reads reality cannot drift from it the way a
marker file can.]

## `support/*`: long-lived maintenance lines

`support_start(version, base)` is a single `git checkout -b support/<version> <base>` — start only,
**no finish or merge-back**. That matches the scope of nvie's own `git-flow` tool for this branch
type, and the reason is structural: a support branch is a permanently diverging maintenance line for
an old release (`base` is normally an old tag like `v1.4.0`), not a short-lived branch that
reconverges. Merging it back would pull old-line code forward into new development.

Attribution worth keeping straight: `support` branches are **not** in nvie's original article, which
documents only feature/release/hotfix. They are a feature of his companion `git-flow` CLI tool
(`git flow support start <release> <base>`, where the base must be a commit on `master`), which is
itself thin on semantics beyond that.

### Patching a support branch

A support branch ships artifacts to production exactly like `main`, so it needs protecting exactly
like `main` — a direct push/commit does not work any more than it would against a protected `main`.
An early design assumed patching needed "no new machinery," just `version.bump` plus a plain
`git tag`; that was wrong.

`support_hotfix_start` / `support_hotfix_finish` / `support_hotfix_finalize` give it the same
PR-mode-primary, two-step shape as a regular hotfix, reusing `_open_pr`/`_next_steps`. Two real
differences, both because a support line is already permanently diverged:

- **No `develop` merge at all.**
- **No release-branch redirect check** — that redirect keeps an active mainline release in sync,
  which has nothing to do with an isolated support line.

Branch naming is `support-hotfix/<support>/<version>`. The `<support>` segment is load-bearing:
`support_hotfix_finish`/`_finalize` need to know which support branch a patch belongs to without any
persisted state, and this tool is stateless throughout — `<support>` is passed explicitly again at
finish and finalize time rather than being remembered.

## What has and hasn't been exercised for real

Verified across four dry-run rounds against scratch repos, with a local **bare** repo standing in
for `origin`: branch-then-bump ordering, the hotfix redirect (including the expected conflict), tags
landing on the correct commits, `main`/`develop` converging, `*_finalize`'s fetch → ff-only → tag →
push → `sync/<tag>` sequence, and `support_hotfix` in both modes.

Those dry runs stopped at the `gh pr create` calls, since `gh` refuses a bare remote with
`none of the git remotes configured for this repository point
to a known GitHub host`.
`tests/integration/test_gitflow_twin_integration.py` closes that gap against a protected GitHub
repo. It covers:

- feature, release with a candidate, and hotfix, each through `*_finish`, a real `gh pr merge` and
  `*_finalize`;
- the release twice, squash-merged and merge-committed;
- the hotfix redirect into an open release branch, including its conflict;
- the tag-exists guard, in its real state: a sync PR left unmerged, so develop is behind main;
- a reused feature name resolving to its newer open PR;
- finalize deleting the finished branch locally and on origin, and a hotfix after a finished release
  in the same clone syncing into develop;
- a start refusing a base that is behind origin.

All eleven green 2026-09-28. Set `REPO_TASKS_GITFLOW_TWIN=TheodoreAD/repo-tasks-gitflow-twin` to run
it; without that it skips, because it needs `gh auth` and leaves PRs and tags in a public repo.

The twin is
[`TheodoreAD/repo-tasks-gitflow-twin`](https://github.com/TheodoreAD/repo-tasks-gitflow-twin), a
permanent public repo seeded with a `pyproject.toml` and a `tasks.py` importing `repo_tasks.ns`.
`main` and `develop` carry a ruleset with an **empty bypass list**: changes go through a pull
request, with no required approvals, and deletion and force-push are blocked. A direct push is
therefore rejected even for the owner, unlike classic branch protection, which lets an admin through
with a warning. Tags carry no rule, because `*_finalize` pushes its tag directly.

### Why the twin is shaped this way

[DECISION: **permanent, not created and deleted per run.** Repeated create and delete cycles would
make GitHub's own soft-deletion and rename-cooldown behaviour a second source of failures, and
disposability buys nothing. Leftover state from a failed run, such as a stray branch, an unmerged PR
or an odd conflict, is kept for a human to read rather than cleaned away. Recovering a real messy
repo is how `gitflow.py`'s recovery paths and messages get better.]

[DECISION: **public**, because GitHub Free offers branch protection and rulesets on public repos
only. A private twin would need a paid plan to be protected, and protection is the point: it is the
one thing a bare local remote structurally cannot test. The seed is generic, so nothing sensitive is
exposed.]

[DECISION: **a ruleset with an empty bypass list, not classic branch protection.** The tests run as
the owner, and classic protection lets an admin push straight through with a warning. That is how
the owner's other personal repos behave, and it would let the exact failure the twin exists to
catch, a direct push instead of a PR, succeed silently. **0 required approvals**, because a sole
account cannot approve its own PR.]

[DECISION: **the tests derive their starting state from the twin.** A permanent repo accumulates
tags and branches, so nothing may assume a clean one. Versions are read off `develop`/`main` as they
stand, feature names are unique per run, and each test uses a **fresh clone**, so no test's outcome
depends on which ran first. The fresh clones are also why the tests first missed the one bug a
long-lived clone has: finished release branches left behind, see "Known bad states". A test now
builds that history inside one clone on purpose.]

What the runs showed beyond pass or fail:

- A squash-merged release's `sync/<tag>` PR does **not** conflict with develop. The bump commits
  live only on the release branch, so develop's version line is untouched between syncs, and the
  squash commit's change applies cleanly. A develop that edited that line itself would conflict, and
  should.
- `gh pr view <branch>` prefers an **open** PR over an older merged one of the same name. That is
  the safe answer for `_require_merged_pr`, since an old merge cannot let finalize proceed past an
  unmerged new PR.
- Rebase merge was not driven. Nothing in `gitflow.py` depends on the strategy beyond the PR state,
  which held for squash and merge commits alike.

[PITFALL: bump-my-version's rc tags are **annotated**, while `_finalize`'s `git tag` is
**lightweight**. So `git ls-remote origin refs/tags/<tag>` returns a tag object's SHA for one and a
commit's for the other. The twin test's first run failed on exactly that, comparing an rc tag to
`HEAD`. Anything comparing tags to commits has to peel (`<ref>^{}`).]

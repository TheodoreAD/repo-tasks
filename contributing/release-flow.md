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

Teams that do not want a release branch for every release are a separate design —
`plans/2026-08-25-release-without-release-branch.md`.

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

**Not verified:** the `gh pr create` calls themselves. Every dry run reached them with exactly the
expected arguments and then stopped at
`none of the git remotes configured for this repository point
to a known GitHub host`, which is the
correct boundary for a non-GitHub remote. They are covered by unit tests only. Closing this gap is
what `plans/2026-08-19-gitflow-test-repo-twin.md` exists for.

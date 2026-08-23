# Release flow

How gitflow is applied in `src/repo_tasks/gitflow.py` — what each flow does, why it is shaped that
way, and where it can leave you stuck. For what a version _number_ is and how it is written across
python/docker/helm, see [`versioning.md`](versioning.md).

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

| task                                       | does                                                                                                         |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `feature_finish(name)`                     | push branch, open PR against `develop`, stop. Nothing further — a feature has no version or tag to finalize. |
| `release_finish()` / `hotfix_finish()`     | push branch, open PR against `main`, stop. **No tag yet, no develop merge yet.**                             |
| `release_finalize()` / `hotfix_finalize()` | run _after_ a human merged that PR, from the same branch.                                                    |

`*_finalize` does: `git fetch origin main` → `git checkout main` → `git merge --ff-only origin/main`
→ tag the now-updated tip → push the tag → branch `sync/<tag>` off that same updated `main` → open a
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

### Everything else

Recovery procedures for the other reachable bad states — an abandoned release branch, a tag pushed
to the wrong commit, `*_finalize` run before the PR actually merged, a `sync/<tag>` PR closed
without merging — are **not documented yet**. See
`plans/2026-08-23-contributing-docs-completion.md`.

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

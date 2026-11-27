---
status: idea
updated: 2026-11-08
source_repo: github.com-personal/hekate
source_session: 5f84bc91-7291-42b4-9474-846d42d45b23.jsonl
source_moment: 2026-11-08T16:47:49Z
source_plan:
---

# gitflow.feature-finish opens a PR with a placeholder title and body

## Context

`inv gitflow.feature-finish <name>` opens its PR through `_open_pr` with the title `Feature: <name>`
and the body `Merging feature/<name> into develop.` (`src/repo_tasks/gitflow.py`, `feature_finish`,
at v0.6.0). Neither says what the change is for.

In a repo that squash-merges, the PR is the permanent record: the branch's commits, and the bodies
written on them, are folded into one commit on `develop` whose subject and body come from the PR or
from whatever the merger types. A placeholder there either lands on `develop` verbatim or has to be
replaced by hand every time. The home instructions apply the full commit-body rule to
`gh pr create --body` for exactly this reason.

Hit while dogfooding the task in hekate, which uses gitflow with squash-merge only: PR #1
(`TheodoreAD/hekate#1`) opened as "Feature: scaffold" with the placeholder body, and was fixed by
hand with `gh pr edit` before merging.

## Evidence

- hekate PR #1, opened by `inv gitflow.feature-finish scaffold` from repo-tasks v0.6.0, then
  retitled and re-described with `gh pr edit 1` before `gh pr merge 1 --squash`.
- The cited session, at `source_moment`.

## Open questions

[NEEDS CLARIFICATION: where the title and body should come from. Candidates: `--title`/`--body`
flags passed through to `gh pr create`; `gh pr create --fill`, which takes them from the branch's
commits (one commit gives its subject and body; several give the first subject and a commit list);
or opening the PR in the editor. `--fill` needs nothing new from the caller, but with several
commits its body is a list rather than a reason.]

[NEEDS CLARIFICATION: whether `release_finish`, `hotfix_finish` and the finalize PRs share the
problem. They call the same `_open_pr`, but their titles name a version, which may be enough.]

## Recommended direction

- Default to `gh pr create --fill`, and accept optional `--title`/`--body` that override it, so the
  common single-commit feature gets a real description with no extra typing.
- Quote both through `shlex.quote` as `_open_pr` already does.

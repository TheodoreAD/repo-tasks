---
status: landed
updated: 2026-09-04
source_repo: github.com-personal/power-user-linux-setup
source_session: bc30285c-145c-494d-b2d1-be6b37cd37f1.jsonl
source_moment: 2026-09-04T13:05:21+03:00
---

# `power-user-linux-setup` is clear of Node 20, and the `artipacked` question is answered

Folds into `plans/2026-08-28-node20-action-deprecation.md`'s "What is left, and where it goes"
table, which lists this repo as one of three still carrying the deprecation. Filed rather than
edited into that plan directly, since the session was working in `power-user-linux-setup`.

`agent-skills` and `scaffoldapy` — including `scaffoldapy/template/.github/workflows/`, still the
only site producing new instances — remain.

## What landed

Three commits on `master`, pushed 2026-09-04, split the way that plan's direction 2 asks for: the
annotated deprecation apart from the plain currency drift.

| action                       | sites | was      | now       | GitHub annotated it? |
| ---------------------------- | ----- | -------- | --------- | -------------------- |
| `actions/checkout`           | 4     | `v4`     | `v7`      | yes                  |
| `actions/setup-python`       | 1     | `v5`     | `v7`      | yes                  |
| `astral-sh/setup-uv`         | 3     | `v9.0.0` | `v10.0.1` | no                   |
| `peaceiris/actions-gh-pages` | 1     | `v4`     | unchanged | n/a — current        |
| `devcontainers/ci`           | 1     | `v0.3`   | unchanged | n/a — current        |

The last two are current at the precision each pin states (latest `v4.1.0` and a `v0.3.x` tag),
which is the comparison rule `ci.check-actions` implements. Recorded so the next sweep does not
re-derive it.

Each major's breaking change was read against this repo rather than assumed, and the plan's
`v5`/`v6`/`v7` reading held: `checkout` v5's minimum runner is self-hosted-only and every job here
is `ubuntu-latest`; v6 changes where credentials persist, not the `persist-credentials` input; v7's
fork-PR block needs `pull_request_target` or `workflow_run`, which no workflow here uses.
`setup-python` v7 additionally removes a `pip-install` input this repo never set. `setup-uv` v10
disables the cache for `pull_request_target`, `workflow_run` and `release` — this repo triggers on
`push`, `pull_request` and `workflow_dispatch` only.

## The `artipacked` question, answered by dropping it

That plan's `NEEDS CLARIFICATION` asked whether checkout v6's separate-credential-file mechanism
retires `devcontainer.yml`'s `# zizmor: ignore[artipacked]` suppression. It does not. Dropped,
bumped to v7, ran the gate: zizmor flags the v7 site identically, because it audits the `uses:`
block's inputs and not where the action stores the credential. Restored, with the retest written
into the comment so the next reader does not repeat it.

The suppression is genuinely load-bearing, not inherited caution — that job force-pushes the
`stable` tag with the checkout's own credentials, so `persist-credentials: false` would break the
thing being flagged. Note also that the finding is `low`/`help` and does not fail the gate on its
own; it was restored on the argument that a permanently-present accepted finding is how a real one
later goes unread.

[PITFALL: **that plan says "the two `# zizmor: ignore[artipacked]` suppressions"; there is one.**
The second went with the `stefanzweifel/git-auto-commit-action` step deleted from `devcontainer.yml`
on 2026-09-01 — the CI-job-commits-to-master removal. Worth correcting in the table rather than
leaving a count that sends the next session looking for a site that no longer exists.]

## Verified by annotation, not by conclusion

Direction 4's check, run against both runs of the same workflow one push apart. Before (`53b88d0`,
run `33864487597`), all three jobs green:

```
warning | Node.js 20 is deprecated. ... actions/checkout@v4, actions/setup-python@v5
warning | Node.js 20 is deprecated. ... actions/checkout@v4
warning | Node.js 20 is deprecated. ... actions/checkout@v4
```

After (`08456b6`, run `33866082588`), all three jobs green:

```
[] no annotations
[] no annotations
[] no annotations
```

The Pages run's single job is clean too. The absence was checked against a call known to work — the
same `gh api repos/<owner>/<repo>/check-runs/<job-id>/annotations` invocation returns the warnings
on the older run — rather than trusted on its own, per that plan's own note about `[]` meaning two
different things.

## One thing to carry into the remaining two repos

A version bump can invalidate a comment, and the gate cannot see it. `publish_on_push.yml` explained
`persist-credentials: false` by saying the credentials would otherwise be left "in `.git/config`" —
true through v5, false from v6, and nothing in `actionlint`, `zizmor` or the test suite reads
English. Committed as its own fix. Worth a grep for `.git/config` in `agent-skills` and
`scaffoldapy` while bumping them.

[DEFERRED: **`power-user-linux-setup` publishes no `ci` namespace, and wiring it today would ship
the wrong version.** Its `tasks/__init__.py` adds no `ci` collection, so `inv ci.status` and
`inv ci.check-actions` do not exist there and every annotation and version comparison above was done
with raw `gh api` calls. Wiring the collection is one line — but the `repo_tasks` resolved into that
repo's venv predates both `e51e062` (the annotation printing) and `9f3a03f` (`check_actions`), so
what it would publish is a `ci.status` that reads `conclusion` only: the exact blind spot this
deprecation hid in. Its `branch` also defaults to `main` against a repo on `master`.

So the two halves have to land together — a `repo_tasks` bump in that repo's `pyproject.toml`/lock,
then the collection — and the bump was deliberately not taken mid-session while `repo-tasks` itself
was being worked on. Worth doing as one change afterwards, and worth checking whether `scaffoldapy`
and `agent-skills` publish the namespace either.]

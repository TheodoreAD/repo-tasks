---
status: idea
updated: 2026-09-08
source_repo: github.com-personal/agent-skills
source_session: 70e28d42-9a4b-4f09-8f22-19112ce49d1b.jsonl
source_moment: 2026-09-08T14:30:00Z
---

# `2026-08-28-node20-action-deprecation.md` has no blockers left

## Context

That plan's last outstanding call site was `agent-skills`, and it was bumped to
`actions/checkout@v7` on 2026-09-08 in commit `450cf68`, pushed to `main` and green on both the
Linux and the Windows job. Both workflows there were on `@v4`: `.github/workflows/ci.yml` and
`.github/workflows/tests-windows.yml`.

So the family-wide item is done — `repo-tasks`, `power-user-linux-setup`, `scaffoldapy` and now
`agent-skills` are all on `@v7`, and nothing on this machine still targets Node 20. The plan can be
retired on its own terms rather than kept open on a blocker that no longer exists.

Filed rather than performed because writing into another repo's working tree is out; this is only
the notification.

## Evidence

Session `70e28d42-9a4b-4f09-8f22-19112ce49d1b.jsonl` under
`~/.claude/projects/-home-tdumitrescu-projects-github-com-personal-agent-skills/`, 2026-09-08. The
distinctive phrase to search that transcript for is "the family's last Node 20 call site".

The bump was driven by a plan filed here for `agent-skills`, absorbed there in commit `34a9599` and
carried out in `450cf68`. Its own commit message records why none of the three majors reaches those
jobs: `v5`'s minimum runner version binds only self-hosted runners and both jobs are hosted, `v6`'s
separate credentials file is moot because both checkouts already set `persist-credentials: false`,
and `v7`'s fork-checkout block applies to `pull_request_target` and `workflow_run`, neither of which
those workflows use.

The repro for the state this clears, from `agent-skills`:

```shell
rg -n --hidden 'actions/checkout@' .github
```

[PITFALL: `--hidden` is not optional. `rg` skips dot-directories by default, so a bare
`rg 'actions/checkout@' .` over a repo root returns nothing while `.github/workflows/` sits right
there — and an empty result reads exactly like "already on v7". Carried over from the filing plan,
where it cost a wrong answer before being caught.]

## Open questions

[NEEDS CLARIFICATION: does the node20 plan have anything left in it beyond the blocker, or is it a
straight retire? It also tracked the two `publish.yml` SHA pins at `v7.0.1` here, which are a
separate concern with its own upkeep — if those are still live the plan's content needs a permanent
home before it is deleted, per `plan-docs`' retire rule.]

[NEEDS CLARIFICATION: is anything else in the family still on a Node 20 action other than
`actions/checkout`? Only checkout was measured. `astral-sh/setup-uv` and `actions/setup-python` were
already current where they appear, but that was read from the repos that were being changed, not
swept across all four.]

## Recommended direction

Re-run the sweep to confirm rather than trusting this note — one command per repo, and it is the
same one either way. Then retire `2026-08-28-node20-action-deprecation.md` if nothing else is
holding it open, and correct its status line, which currently reads as blocked on a `repo-tasks`
consumer sweep reaching `agent-skills`. That framing was itself wrong and was corrected in the
filing plan: `agent-skills` is not a `repo-tasks` consumer at all — no such import in its tasks, no
bootstrap script — so it was never waiting on the sweep, which is why nothing reached it for eleven
days.

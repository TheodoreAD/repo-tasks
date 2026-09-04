---
status: idea
updated: 2026-09-04
---

# An advisory that lands with no push here is not seen until the next push

## Context

Carried out of the now-retired `plans/2026-08-30-deps-audit-in-ci.md`, which built the audit
workflow and explicitly declined to re-decide this.

`security.yml` runs `uv audit --locked` on push to `main` and on manual dispatch. That is the right
trigger for a check whose answer changes when the code changes — and this one's answer changes when
**the OSV database** changes, which is not an event this repo produces. A repo nobody pushes to for
three weeks is not audited for three weeks, and the last run stays green on its badge throughout.

**The obvious fix is a schedule, and this repo has already ruled one out.**
[`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Nothing here runs on a
schedule, and that is the decision", settled 2026-08-30 across the three items that carried the
trade-off: a red scheduled run has no audience in a repo that pushes straight to `main` and reviews
no PRs, and an unwatched scheduled job looks like coverage without being it. That decision
explicitly left the audit's _trigger_ open, which is what the push trigger then filled.

**The tension is real, and it is a genuinely different argument rather than a re-litigation.** The
2026-08-30 decision was about staleness — an action three majors behind, a config that has drifted.
Staleness needs a reader: nothing bad happens until someone acts on the report, so a report nobody
reads is worth nothing and the honest move is not to generate it. A vulnerability is not like that.
The exposure exists whether or not anyone reads the run, and the value of knowing is not that
someone acts within the hour but that the gap between disclosure and discovery stops being
unbounded.

Worth stating plainly because it is the crux: **the "no audience" argument assumes the run's only
product is a notification.** For an advisory, the run's product is also a dated record of when this
repo's lock was last known clean, and that has value with no reader at all.

## Open questions

[NEEDS CLARIFICATION: does the counter-argument actually survive contact with how these repos are
used? The strongest version of the 2026-08-30 decision is not "nobody reads it" but "a permanently
red badge trains its owner to ignore the badge" — and an advisory with no fix available produces
exactly that, which this repo has already lived through for four days on `setuptools`. If a
scheduled run can sit red for a week with nothing to do about it, it may degrade the signal in
precisely the way the original decision feared, and the advisory-versus-staleness distinction would
not save it.]

[NEEDS CLARIFICATION: if not a schedule, is there a trigger that fires on the event that actually
matters? The event is "OSV published something affecting a package in this lock", which is not a
GitHub event this repo can subscribe to. GitHub's own Dependabot alerts are the native mechanism for
exactly this and were never priced in the original plan — they need no workflow, no schedule and no
uniformity mechanism, and they notify rather than colouring a badge. Their cost is that they are
per-repo GitHub configuration rather than a file, which cuts against the make-it-identical-in-every-
repo constraint that shaped the whole design.]

[NEEDS CLARIFICATION: whichever way this goes, does it have to be uniform across the family? That
constraint was binding for the audit itself — per-repo drift being the thing that is hard to track —
but it may not bind a _trigger_. A schedule on `repo-tasks` alone, as the repo that hosts the
reusable workflow and moves most often, might be worth more than nine schedules and cheap enough to
not need the argument settled family-wide.]

## Recommended direction

Rough, and behind the questions above.

Do not add a `cron` quietly. The value of the 2026-08-30 decision is that it was made explicitly and
recorded, and the failure mode to avoid is a scheduled workflow appearing in a later commit because
it was convenient, which leaves two contradictory positions in the repo with no note saying which
won.

The line most likely to hold is that this is not a scheduling question at all but a notification
one, and that Dependabot alerts answer it without touching the workflow design or the no-schedule
decision. That would leave `security.yml` exactly as it is — the gate for what this repo pushes —
and put the "something changed underneath you" case on the mechanism GitHub built for it. Worth
pricing that properly before reopening the schedule argument, since it may make the argument moot.

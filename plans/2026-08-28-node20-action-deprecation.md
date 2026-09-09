---
status: landed
updated: 2026-09-10
---

# The family's pinned actions target a deprecated Node, and the template ships it onward

## Context

Every CI run in the family carries an annotation nobody reads, because the run is green:

```
Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run
on Node.js 24: actions/checkout@v4. For more information see:
https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
```

Found 2026-08-28 while reading the annotations on an unrelated green run. GitHub is currently
_forcing_ these onto Node 24 rather than failing them, so the whole thing is invisible from a
pass/fail signal — which is exactly why it has sat since the 2025-09-19 changelog, roughly eleven
months.

The flagged set was taken from GitHub's own annotations on the latest run of each repo, not inferred
from the action list — the two differ, and guessing would have over-scoped the work:

| repo                     | flagged by GitHub                                |
| ------------------------ | ------------------------------------------------ |
| `repo-tasks`             | `actions/checkout@v4`                            |
| `power-user-linux-setup` | `actions/checkout@v4`, `actions/setup-python@v5` |
| `scaffoldapy`            | `actions/checkout@v4`                            |
| `agent-skills`           | `actions/checkout@v4`                            |

Everything else in use is already clean and needs no work: `astral-sh/setup-uv` (10 at `@v9.0.0`, 2
hash-pinned), `peaceiris/actions-gh-pages@v4`, `docker/login-action@v3`, `devcontainers/ci@v0.3`,
`stefanzweifel/git-auto-commit-action@v7`.

### How far behind, and where

15 `actions/checkout` call sites, plus one `actions/setup-python`. Current upstream is
**`checkout@v7.0.1`** (2026-07-20) and **`setup-python@v7.0.0`** (2026-07-20) — three majors back in
both cases, so this is a catch-up, not a nudge.

Two of those call sites are different in kind: `repo-tasks`'s `publish.yml` hash-pins
`actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4` (twice), per the pinning decision
in [`../contributing/quality-gate.md`](../contributing/quality-gate.md) and the `unpinned-uses`
policy in the shipped `zizmor.yml`. Those need a re-resolved SHA rather than a version bump —
`v7.0.1` is `3d3c42e5aac5ba805825da76410c181273ba90b1`, resolved 2026-08-28, and worth re-resolving
at the time of the change rather than trusting this line.

[PITFALL: the one call site that matters most is not in any of these four repos' own CI.
`scaffoldapy/template/.github/workflows/` carries `checkout@v4` too, so every repo generated from
here inherits the deprecation at birth. **Fixed — the template is on `@v7` as of the 2026-09-08
measurement below**; kept because the shape recurs with the next deprecation and this is where it
was first named. The blast radius grew with each generation, and a generated repo's owner had no
reason to suspect it. This is the same "true of scaffoldapy's own tree, false of what it generates"
shape that [`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) records for
`failOnWarnings`.]

### What actually changed across the majors

Read from the upstream release notes rather than assumed, because two of the three are not routine:

- **`checkout@v5.0.0`** (2025-08-11) — the Node 24 move itself. Declares a **minimum runner version
  of v2.327.1**; irrelevant on GitHub-hosted runners, load-bearing for anything self-hosted.
- **`checkout@v6.0.0`** (2025-11-20) — "persist creds to a separate file". This one touches work
  done in this family on 2026-08-26: `persist-credentials: false` was added to every checkout to
  satisfy zizmor's `artipacked`, and `power-user-linux-setup`'s `devcontainer.yml` carries a
  `# zizmor: ignore[artipacked]` suppression. Whether it is still needed under v6's mechanism was a
  real question, not a formality — answered under "Open questions" below: it is.
- **`checkout@v7.0.0`** (2026-06-18) — blocks checking out a fork PR under `pull_request_target` and
  `workflow_run`, plus an ESM rewrite. A genuine behavioural change, though these repos take no fork
  PRs, so the risk here is low and the security default is the one we want anyway.
- **`setup-python@v6.0.0`** (2025-09-04) — explicitly labelled a breaking change: upgrade to
  Node 24.

## Measured and cleared 2026-09-08, verified here 2026-09-09: the family is entirely on `@v7`

When this section was written the status line read "blocked on the batched consumer sweep reaching
`scaffoldapy` and `agent-skills`", and half of that was already discharged. Every `actions/checkout`
and `actions/setup-python` in the family, read directly:

| repo                     | state                                                                |
| ------------------------ | -------------------------------------------------------------------- |
| `repo-tasks`             | `@v7` throughout, plus the two `publish.yml` SHA pins at `v7.0.1`    |
| `power-user-linux-setup` | `@v7` throughout, `setup-python@v7`, `artipacked` suppression intact |
| `scaffoldapy`            | `@v7` in its own `ci.yml` **and in `template/.github/workflows/`**   |
| `agent-skills`           | `@v7` in `ci.yml` and `tests-windows.yml` — **cleared 2026-09-08**   |

**The template is done, which is the item this plan called the highest-leverage one.** Its `PITFALL`
above says every repo generated from `scaffoldapy` inherits the deprecation at birth; that is no
longer true, and the blast radius the plan worried about has stopped growing.

`agent-skills` was the only site left, at two call sites, and it read `@v4` when this section was
first written. It is also worth noting that it is **not a `repo-tasks` consumer** — no
`from repo_tasks` in its tasks, no bootstrap script — so folding it into "the batched consumer
sweep" was a category error from the start. It needed an action bump, not a sweep, which is why
nothing reached it for eleven days.

### It was cleared the same day, and the loop is worth recording

Merged in from `2026-09-08-node20-blocker-cleared-by-agent-skills.md`, filed back here by the
`agent-skills` session that did the work and absorbed 2026-09-09 — the name to search for with
`plans.py archive` if the original filing is wanted.

[PITFALL: **the filing and the clearing were hours apart, and this plan went on saying `blocked` for
a day** — the same rot this session had spent that day cataloguing in nine other plans, arriving on
the one edit made to fix it. The status was corrected only because a harvest read the store queue;
nothing about landing the work in `agent-skills` touches the plan here that names it as a blocker.
That asymmetry is the whole argument of `agent-skills`'
`2026-09-08-stale-claims-in-live-plans-have-no-prompt.md`, filed the same day, and this is its
cleanest instance: cross-repo, both halves done correctly, and still stale in between.]

A plan filed from here for `agent-skills` was absorbed there (`34a9599`) and carried out in
**`450cf68`**, pushed to `main` and green on both the Linux and the Windows job. That session's own
commit message records why none of the three majors reaches those workflows, checked against them
rather than in the abstract: `v5`'s minimum runner version binds self-hosted runners only and both
jobs are hosted, `v6`'s separate credentials file is moot because both checkouts already set
`persist-credentials: false`, and `v7`'s fork-checkout block applies to `pull_request_target` and
`workflow_run`, neither of which those workflows use.

**Verified here rather than taken on trust**, 2026-09-09, which is what the filing plan asked for:
`rg -n --hidden 'actions/checkout@' <agent-skills>/.github` returns `@v7` at both sites. So no
`actions/checkout` or `actions/setup-python` anywhere in the family still targets Node 20.

**The filing plan's second open question is answered too.** It asked whether anything _other_ than
`actions/checkout` is still on a Node 20 action, noting that only checkout had been measured. Swept
across all four repos plus `scaffoldapy`'s template on 2026-09-09, and `inv ci.check-actions` run
here: **0 of 3 actions behind** in this repo, and nothing in the family on a version this plan's
survey flagged. One residue, and it is a currency question rather than a Node one — **two
`astral-sh/setup-uv@v9.0.0` call sites against twelve at `@v10.0.1`**, both outside this repo, so
each repo's own `ci.check-actions` owns it.

[PITFALL: **`rg` skips dot-directories by default, so the first pass over the template reported no
workflows at all.** `rg 'uses: ' <repo>/template` returns nothing while
`template/.github/workflows/ci.yml` sits right there, because `.github` is hidden — `--hidden` is
what finds it. This is the same silent-empty-result trap `~/AGENTS.md` documents for `fd`, and it
applies to `rg` identically. It matters here specifically: the template is the site this plan cares
about most, its path is hidden, and an empty result reads exactly like "already clean".]

## Open questions

~~Does this become a shipped concern or stay per-repo?~~ Resolved 2026-08-29, and the answer turned
out to be both, split along a line the question did not see: **workflow files stay per-repo, the
means of noticing ships**. `configs.pull` still distributes no `.github/workflows/`, and should not
— but `ci.status` and `ci.check-actions` are tasks, so every consumer gets the detection the moment
it updates `repo-tasks`, and each repo's bump stays its own hand-edit. That is the durable answer to
"the question will recur with the next deprecation": next time it recurs into a task that is already
watching.

~~`v7` or `v5`?~~ **`v7`**, settled 2026-08-29 when the first repo was actually done. Each of the
three majors' changes was checked against this family rather than in the abstract, and none reaches
it: v5's minimum runner v2.327.1 is a self-hosted concern and every job in every one of these repos
is `ubuntu-latest`; v6 changes where credentials are persisted, not the `persist-credentials` input,
which stays `false` at every site; v7's fork-PR block applies to `pull_request_target` and
`workflow_run`, which no workflow here uses. The `artipacked` interaction this was waiting on is
`power-user-linux-setup`-only and does not gate the other three repos.

~~Do the `# zizmor: ignore[artipacked]` suppressions survive the upgrade?~~ **They do, answered
2026-09-04 by dropping one and running the gate.** v6's separate-credential-file mechanism does not
retire it: zizmor audits the `uses:` block's inputs, not where the action stores the credential, so
the v7 site is flagged identically to the v4 one. Restored, with the retest written into the comment
so the next reader does not repeat it.

The suppression turned out to be load-bearing rather than inherited caution — that job force-pushes
the `stable` tag with the checkout's own credentials, so `persist-credentials: false` would break
the thing being flagged. It was restored even though the finding is `low`/`help` and fails no gate
on its own, on the argument that a permanently-present accepted finding is how a real one later goes
unread.

[PITFALL: **this plan said "the two suppressions"; there is one.** The second went with the
`stefanzweifel/git-auto-commit-action` step deleted from `devcontainer.yml` on 2026-09-01 — the
CI-job-commits-to-master removal — so the count was stale by three days when it was acted on.
Corrected here rather than left to send the next session looking for a site that no longer exists.]

### Should a task check this, and fix it?

Raised by the user 2026-08-28, immediately after the plan landed: "shouldn't we have a task to check
whether any of these versions are behind and fix it in our files?" Researched rather than answered
from instinct, because the framing hides two different questions with different best answers.

**The hard constraint first:** currency cannot be a gate step. Answering "is this behind?" requires
asking a remote registry, and `quality.check` is offline and deterministic in every consumer by
design. Anything here is a standalone `@requires(NETWORK)` task, the same shape as the CI dependency
audit — worth noting as a sibling: both are network-only currency checks that the gate cannot host,
and the audit's design is the one to follow, since it went first. It landed 2026-08-31 as its own
workflow, and its reasoning is in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md), "The dependency audit runs as
its own workflow".

**Question A — "is anything deprecated or warning?"** GitHub already computes this and hands it over
free, as run annotations. `ci.status` (`src/repo_tasks/ci.py`) already calls `gh run list --json`
and already stops on a failed conclusion — but it reads `conclusion` and nothing else, which is
precisely the blind spot that hid this issue: the 2026-08-28 run of `d941fc7` reported `✓ main CI`
while carrying four Node 20 annotations, one per job. Annotations are one further call
(`gh api repos/<owner>/<repo>/check-runs/<job-id>/annotations`).

[DECISION: prefer surfacing annotations over building a version-currency checker, if only one gets
built. It needs no version oracle, no new dependency and no extra network beyond a call the task is
already making, and it catches every future deprecation class — runner images, action archival, the
next Node bump — rather than only the one that prompted it. Letting GitHub be the oracle is strictly
more general than reimplementing its judgement.]

**Superseded 2026-08-29: both were built, because the premise "if only one" turned out to be the
wrong frame.** The measurement below showed annotations cover one third of what was actually stale
here. The decision above is still right about which is more _general_ — it just is not a substitute
for the other.]

**Question B — "is anything behind latest, and fix the files?"** This is the part with real prior
art, and per `~/AGENTS.md` it should not be hand-rolled. Surveyed 2026-08-28:

| tool                                                                        | fit                                                                                                                                         |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| [Dependabot](https://docs.github.com/en/code-security/) (`version-updates`) | native, free, no install; opens a PR per bump — the friction against this family's direct-to-main habit                                     |
| [`pinact`](https://github.com/suzuki-shunsuke/pinact)                       | pins _and_ updates, and verifies the `# v4`-style version comment — the only surveyed tool that handles `publish.yml`'s hash pins correctly |
| [`ratchet`](https://github.com/sethvargo/ratchet)                           | same space; Renovate understands its `# ratchet:` comments                                                                                  |
| [`actions-up`](https://github.com/azat-io/actions-up)                       | interactive, warns on major bumps; interactivity is wrong for a task                                                                        |
| [Renovate](https://docs.renovatebot.com/modules/manager/github-actions/)    | most configurable, heaviest to adopt                                                                                                        |

[PITFALL: `pinact` is the best technical fit and the worst install fit. None of `pinact`, `ratchet`,
`actions-up` or a `*-py` wrapper of any of them exists on PyPI (checked directly, 2026-08-28) — only
`gha-update`, at 2 releases and a 5 KB pure-python wheel, which is too little adoption to lean on.
So adopting `pinact` means a Go-binary install method in `setup.toml` rather than the `uv-tool` one
mechanism everything else here uses. That cost is the real decision, not the tool's merits.]

~~A or B, or both?~~ **Both**, decided 2026-08-29 on the measurement rather than the instinct. The
premise that "B's value is mostly one-off" was wrong: A cannot see plain currency drift at all, so
without B the two thirds of this repo's staleness that GitHub never annotated stays invisible
forever, not just once.

~~If B, Dependabot or a task?~~ **A task, and detect-only** — but the real decision was not the one
this question asked. Pricing Dependabot honestly against direct-to-main was the wrong axis; what
settled it was that doing all five bumps by hand cost minutes, and every bit of that cost was
reading each major's release notes to decide whether its breaking change reaches these repos.
Dependabot and `pinact` both automate the edit and leave that judgement undone, handing over a green
PR whose risk is unread — which on repos that push through a branch-protection bypass is worse than
no tool, because nothing downstream forces the read. A detector inverts it: it automates the part
that gets forgotten and leaves the part that needs judgement to whoever is reading. `pinact`'s
Go-binary install method, the objection recorded in the pitfall above, never had to be priced.

## Recommended direction

Rough — the questions above come first, particularly the `v5`-vs-`v7` one.

1. **Do the template first, not last.** `scaffoldapy/template` is the only call site that keeps
   producing new instances of the problem; every generation before the fix is another repo to chase.
   Its e2e tier renders every combination and runs the generated repo's own gate, so the change is
   verifiable there rather than by inspection.
2. **Bump the plain version refs, re-resolve the two pinned SHAs.** These are separate operations
   with separate failure modes, and mixing them into one commit makes the pinned pair easy to miss.
   Re-resolve the SHA at the time of the change; do not copy the one recorded above.
3. **Drop the `artipacked` suppressions and let the gate rule on them**, rather than carrying them
   across on the assumption they are still needed. Done for `power-user-linux-setup`, the only repo
   that had one; the gate ruled it still needed.
4. **Verify by annotation, not by conclusion.** The whole reason this went unseen is that a green
   run looks identical either way, so the check that closes this plan is re-reading the annotations
   on a post-change run of each repo — `gh api repos/<owner>/<repo>/check-runs/<job-id>/annotations`
   — and confirming the Node 20 message is gone. A passing CI run proves nothing here.

~~The standing-check question is separate work and should not hold up clearing the deprecation.~~
**Discharged 2026-08-29**: both halves were built rather than deferred (`e51e062`, `9f3a03f`), and
the deprecation cleared regardless.

## Landed: `repo-tasks` (2026-08-29)

The first of the four repos, done here because the session was already in it and the work is
self-contained. `e8837b1` bumped the three plain refs `v4` -> `v7`; `a9cb3d9` re-pinned
`publish.yml`'s two hash sites. Split deliberately, per the direction below — a stale SHA is not a
version mismatch, it is a checkout of something nobody reviewed.

The SHA was re-resolved rather than copied from this file, and came back the same value:

```
gh api repos/actions/checkout/git/ref/tags/v7.0.1 --jq '.object.type + " " + .object.sha'
commit 3d3c42e5aac5ba805825da76410c181273ba90b1
```

A lightweight tag, so the ref is already the commit — no tag object to dereference. `v7.0.1`
(2026-07-20) re-confirmed as current upstream the same day. Gate green: actionlint clean, zizmor
`--offline` no findings.

~~That the annotation is actually gone.~~ **Verified 2026-08-29** on run `33251847669`, the first
after these commits were pushed. All five jobs green — and green was never the question, so it was
checked the only way that answers it:

```
inv ci.status --limit 3
[ci.status] success  CI  2026-08-29T12:10:29Z  .../actions/runs/33251847669
[ci.status] success  CI  2026-08-28T12:33:18Z  .../actions/runs/33171547916
[ci.status] success  CI  2026-08-28T12:26:24Z  .../actions/runs/33171076772
```

Silence where the previous run printed the Node 20 warning. Confirmed against the API directly
rather than trusting an absence —
`gh api repos/<owner>/repo-tasks/check-runs/99098758033/
annotations` returns `[]`, so the call
works and the nothing is real.

Worth recording how that reads: the two runs above it in the same listing are the _old_ workflows,
and they are the ones carrying the warning. The same three lines, from the same command, say
"deprecated" for yesterday and nothing for today. That is the signal this plan set out to make
visible, doing its job on its own fix.

### Then the rest of `repo-tasks`, at the user's direction

`5ea8387`/`ee6a6d8` brought the other two actions current: `astral-sh/setup-uv` `v9.0.0` ->
`v10.0.1` (three plain sites plus two hash pins, SHA `20cfd1bf…`), `docker/login-action` `v3` ->
`v4`. Neither was ever flagged by GitHub — this is plain currency drift, found only by asking the
registry. Every action in this repo is now current.

Both majors' breaking changes were read and checked against this repo rather than assumed, and one
of the two mattered enough to be worth checking: setup-uv v10 disables the cache under
`enable-cache: auto` for `pull_request_target`, `workflow_run` and `release`, as cache-poisoning
defence. No workflow here uses any of those triggers, so it reaches nothing. login-action v4 is the
same Node 24 move as checkout v5, with the same self-hosted-only runner minimum.

### What this settles about question A vs question B

The two halves of today's work are the evidence the open question above was missing, because they
were found by different means and neither means would have found the other:

| action                | behind by | flagged by a GitHub annotation?          |
| --------------------- | --------- | ---------------------------------------- |
| `actions/checkout`    | 3 majors  | **yes** — this plan exists because of it |
| `astral-sh/setup-uv`  | 1 major   | no                                       |
| `docker/login-action` | 1 major   | no                                       |

So **A alone is insufficient**, which the question did not know. Annotations report what GitHub has
decided to deprecate; they say nothing about an action simply being behind. Two thirds of what was
actually out of date here was invisible to A and visible only to B.

The second finding cuts the other way, against B's usual shape. Doing all five bumps by hand took
minutes, and the whole cost was in one place: reading each major's release notes and deciding
whether its breaking change reaches these repos. That judgement is the expensive part, and it is
exactly the part an auto-bumping tool (Dependabot, `pinact`) does not do — it performs the cheap
half and hands over a diff whose risk is still unread. A _detector_ that reports drift and leaves
the bump to a human or agent inverts that: it automates the part that gets forgotten and leaves the
part that needs judgement.

Nothing here has measured how often a major in this family carries a change that actually reaches
these repos, and the sample stayed one-sided to the end. **Moved 2026-09-10 to
[`2026-09-10-action-pinning-and-currency.md`](2026-09-10-action-pinning-and-currency.md)**, which
owns it as an open question — the answer changes the case for report-only, so it outlives this plan.

### A is cheap, and now proven rather than assumed

Walked end to end against a real green run, 2026-08-29:

```
gh run list --branch main --limit 3 --json databaseId,conclusion,workflowName,createdAt
gh api repos/<owner>/repo-tasks/actions/runs/33171547916/jobs --jq '.jobs[] | .id, .name'
gh api repos/<owner>/repo-tasks/check-runs/98849673566/annotations \
  --jq '.[] | .annotation_level + " | " + .message'
warning | Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to
run on Node.js 24: actions/checkout@v4. ...
```

`ci.status` already carries `@requires(GH, NETWORK)`, already calls `gh run list --json`, and
already stops on a failed conclusion. The delta is one field (`databaseId`) plus one call per job —
five jobs on this repo's CI. No new dependency, no new install method, no version oracle.

## What is left, and where it goes

Two repos and one template still carry it. Both are outside this repo, so they join the batched
cross-repo pass already deferred in
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) rather than being done
piecemeal from here:

| repo                     | remaining                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------- |
| `scaffoldapy`            | own CI, **plus `template/.github/workflows/`** — the only site still emitting new instances |
| `agent-skills`           | `checkout`                                                                                  |
| `power-user-linux-setup` | **done 2026-09-04** — see the section below                                                 |

[PITFALL: "do the template first" (direction 1 below) and "repo-tasks first" (what happened) are in
tension, and the tension is real rather than a mistake to correct — the template is the only call
site that keeps producing new instances, so every generation between now and that fix inherits the
deprecation. The mitigation is that no repo is expected to be generated in that window; if one is,
it needs the bump by hand.]

## Landed: `power-user-linux-setup` (2026-09-04)

Merged in from `plans/2026-09-04-node20-power-user-linux-setup-done.md`, which was filed into the
store from a session working in that repo and absorbed here rather than edited into this plan
directly. That file is gone;
`plans.py archive --file 2026-09-04-node20-power-user-linux-setup-done.md` reads it back.

Three commits on `master`, pushed 2026-09-04, split the way direction 2 asks for — the annotated
deprecation apart from the plain currency drift:

| action                       | sites | was      | now       | GitHub annotated it? |
| ---------------------------- | ----- | -------- | --------- | -------------------- |
| `actions/checkout`           | 4     | `v4`     | `v7`      | yes                  |
| `actions/setup-python`       | 1     | `v5`     | `v7`      | yes                  |
| `astral-sh/setup-uv`         | 3     | `v9.0.0` | `v10.0.1` | no                   |
| `peaceiris/actions-gh-pages` | 1     | `v4`     | unchanged | n/a — current        |
| `devcontainers/ci`           | 1     | `v0.3`   | unchanged | n/a — current        |

The last two are current at the precision each pin states (latest `v4.1.0` and a `v0.3.x` tag),
which is the comparison rule `ci.check-actions` implements — recorded so the next sweep does not
re-derive it.

Each major's breaking change was read against that repo rather than assumed, and this plan's
`v5`/`v6`/`v7` reading held: `checkout` v5's minimum runner is self-hosted-only and every job there
is `ubuntu-latest`; v6 changes where credentials persist, not the `persist-credentials` input; v7's
fork-PR block needs `pull_request_target` or `workflow_run`, which no workflow there uses.
`setup-python` v7 additionally removes a `pip-install` input that repo never set. `setup-uv` v10
disables the cache for `pull_request_target`, `workflow_run` and `release`; it triggers on `push`,
`pull_request` and `workflow_dispatch` only.

**Verified by annotation, not by conclusion** — direction 4's check, run against two runs of the
same workflow one push apart. Before (`53b88d0`, run `33864487597`), all three jobs green and all
three carrying `Node.js 20 is deprecated ... actions/checkout@v4`. After (`08456b6`, run
`33866082588`), all three jobs green and all three returning no annotations; the Pages run's single
job is clean too. The absence was checked against a call known to work — the same
`gh api repos/<owner>/<repo>/check-runs/<job-id>/annotations` returns the warnings on the older run
— rather than trusted on its own, per this plan's own note that `[]` means two different things.

[PITFALL: **a version bump can invalidate a comment, and no gate can see it.** `publish_on_push.yml`
there explained `persist-credentials: false` by saying the credentials would otherwise be left "in
`.git/config`" — true through checkout v5, false from v6. Nothing in `actionlint`, `zizmor` or a
test suite reads English, so the sentence would have survived the bump unread. Committed as its own
fix, and worth a grep for `.git/config` in `agent-skills` and `scaffoldapy` while bumping them.]

**`power-user-linux-setup` published no `ci` namespace, and wiring it that day would have shipped
the wrong version.** Its `tasks/__init__.py` added no `ci` collection, so `inv ci.status` and
`inv ci.check-actions` do not exist there and every annotation and version comparison above was done
with raw `gh api` calls. Wiring the collection is one line — but the `repo_tasks` resolved into that
repo's venv predates both `e51e062` (the annotation printing) and `9f3a03f` (`check_actions`), so
what it would publish is a `ci.status` that reads `conclusion` only: the exact blind spot this
deprecation hid in. Its `branch` also defaults to `main` against a repo on `master`. So the two
halves have to land together — a `repo_tasks` bump in that repo's `pyproject.toml`/lock, then the
collection — and the bump was deliberately not taken mid-session while `repo-tasks` itself was being
worked on. Worth doing as one change afterwards, and worth checking whether `scaffoldapy` and
`agent-skills` publish the namespace either.

**Resolved for that consumer 2026-09-05.** The collection was wired there on 2026-09-04 and the pin
bumped to `7bb880b` in the batched sweep the next day
([`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md), "The batched sweep's
first half ran"). Run against the bumped pin, `inv ci.status --branch master --limit 3` printed
three green runs and no annotations, and `inv ci.check-actions` reported `0 of 5 action(s) behind`.
Silence from `ci.status` is the result that matters — the same command printed the Node 20 warning
under green runs there before the bump.

**The ordering hazard above turned out not to have existed, and that was checked rather than
assumed**: `e51e062` and `9f3a03f` were both already ancestors of the _old_ pin `9d57d464`, so the
collection wired on 2026-09-04 was never publishing the blind-spot version. The bump was owed
anyway. Recorded so nobody re-derives it. `--branch master` is still needed on every call there,
since the task's default is `main`; a per-consumer ergonomic rather than a defect, but that consumer
can never use the bare form.

**`scaffoldapy` and `agent-skills` are checked as of 2026-09-10 — both publish the namespace**,
since each `tasks.py` is `from repo_tasks import ns`. That, and the correction that `agent-skills`
was a consumer all along, moved to
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md), which owns the consumer
set.

## Built: both halves (2026-08-29)

`e51e062` — `ci.status` now prints the latest run's `warning` and `failure` annotations. One extra
JSON field (`databaseId`), one call for the run's job ids, one per job for its annotations; messages
deduped across a matrix and rewrapped onto one line. Never raises: an annotation names a deadline,
not a break, and a token that cannot read check runs degrades to no annotations rather than to an
error. Verified against this repo's real history — the Node 20 warning printed under three green
runs, which is the failure mode this plan exists for.

`9f3a03f` — `ci.check-actions`, network-only, report-only. Reads `uses:` out of the workflow files,
asks GitHub for each action's latest release, compares **only at the precision the pin states**.
That comparison is the whole trick and the reason a hand-rolled check is defensible: `@v7` against a
latest of `v7.0.1` is current, because a bare major is a moving tag; `@v9.0.0` against `v10.0.1` is
behind. A string or full-tuple comparison gets the common case wrong. A SHA pin reads its version
from the `# v7.0.1` comment, and a SHA with no comment is its own finding — the same thing zizmor's
`unpinned-uses` policy is asking for. `--path` so it can be pointed at a template's workflows.

Both are `@requires(GH, NETWORK)`, neither is in `quality.check`, and neither exits non-zero on a
finding. Report-only was a deliberate choice, not an omission: nobody's commit runs these, so a
non-zero exit blocks nothing and would only train its reader to ignore the output.

Current state of this repo, from the task itself:

```
[ci.check-actions] actions/checkout@v7  current (latest v7.0.1)  [ci.yml, docker-release.yml]
[ci.check-actions] actions/checkout@v7.0.1  current (latest v7.0.1)  [publish.yml]
[ci.check-actions] astral-sh/setup-uv@v10.0.1  current (latest v10.0.1)  [ci.yml, docker-release.yml, publish.yml]
[ci.check-actions] docker/login-action@v4  current (latest v4.6.0)  [docker-release.yml]
[ci.check-actions] 0 of 3 action(s) behind
```

**Settled 2026-08-30, and not in this plan's favour.** Neither task runs on a schedule and neither
will: [`../contributing/quality-gate.md`](../contributing/quality-gate.md), "Nothing here runs on a
schedule", records the decision for all three items that carried this trade-off — no scheduled
workflow, `ci.status` as a deliberate pre-push step, `ci.check-actions` run by hand when a workflow
is edited, and the residual staleness accepted rather than left pending. The consumer-side half of
the question is still open, in `scaffoldapy`'s own `plans/2026-08-30-scheduled-checks-cadence.md`
(filed there from here on 2026-08-30), because a generated repo with actual reviewers has the reader
this one lacks.

**SHA-pinning every workflow plus dependabot**, and **the checker's inability to tell a truthful pin
comment from a lying one**, both **moved 2026-09-10 to
[`2026-09-10-action-pinning-and-currency.md`](2026-09-10-action-pinning-and-currency.md)**. They
arrived here from the retired quality-gate sweep plan and would otherwise be retired a second time
without an owner; they are one subject with the unmeasured breaking-change rate above, and none of
the three is about Node 20.

**The README's namespace overview is fixed, 2026-09-08 (`56371b1`).** `ad4b84d` had added `ci`
because that session added a task to it; `gitflow` was a pre-existing gap in the same list, named in
the release-flow prose further down but absent from the list that claims to enumerate every
facility.

[PITFALL: **the gap was three times the size it looked, and only counting found the rest.** Reading
the paragraph for plausibility turns up the namespace that is obviously missing; diffing it against
`inv -l` turned up four missing namespaces (`version`, `gitflow`, `trunkflow`, `release`) and six
listed namespaces whose task lists had drifted, including one task named as `claude_hook` that has
never existed under that name. A prose list claiming to enumerate something is checkable
mechanically, and that is the only way it was ever going to be checked — which is the argument
[`2026-09-01-docs-generation-in-precommit.md`](2026-09-01-docs-generation-in-precommit.md) is
already making about generating such lists rather than maintaining them.]

## Migrated to

Retired 2026-09-10. The subject is finished and verified — every `actions/checkout` and
`actions/setup-python` in the family is on `@v7`, the template included — so what is left here is
rationale and residue, and each piece has been given a home.

**[`../contributing/quality-gate.md`](../contributing/quality-gate.md)**, as design rationale:

- "Action currency has two halves, and each is blind to the other" — the A-vs-B measurement (one of
  three stale actions was annotated), the decision to build both after deciding to build one, the
  verify-by-annotation procedure with its `gh api` calls, and three pitfalls: `[]` meaning two
  different things, a version bump invalidating a prose comment, and `rg` skipping dot-directories.
- "Workflow hardening" — how to re-resolve a SHA pin and why the tag object matters, the
  version-refs-and-SHA-pins-are-separate-commits rule, the auto-bumping tool survey with `pinact`'s
  install-fit pitfall, the detector-over-bumper decision, and the `artipacked`-survives-v6 pitfall.

**[`2026-09-10-action-pinning-and-currency.md`](2026-09-10-action-pinning-and-currency.md)**, a new
plan holding everything still open: whether `ci.check-actions` makes pinning every workflow
maintainable, the checker's inability to verify a SHA pin's version comment, and the unmeasured rate
at which a major actually reaches these repos.

**[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md)** — that `scaffoldapy`
and `agent-skills` both publish the `ci` namespace through `from repo_tasks import ns`, and the
correction that `agent-skills` was a consumer all along rather than the non-consumer this plan
recorded.

**Filed for `agent-skills`** as `2026-09-10-setup-uv-pins-two-majors-behind.md` — its two
`astral-sh/setup-uv@v9.0.0` pins, the family's last currency residue, with v10's cache change left
as an open question to read against its own workflows.

Deliberately not migrated:

- **The v5/v6/v7 and setup-python v6/v7 release-note readings.** Every repo is past them, so the
  findings are spent; what was durable was the _method_ — read each major against this family rather
  than in the abstract — and that is the detector-over-bumper decision in `quality-gate.md`.
- **The template-inherits-the-deprecation pitfall.** `ci.check-actions`' `--path` docstring already
  carries it, at the place someone stands when they need it.
- **"The filing and the clearing were hours apart."** `agent-skills` owns that concern in its own
  `2026-09-08-stale-claims-in-live-plans-have-no-prompt.md`; migrating it here would ship a second
  copy that repo would then have to keep in step.
- **The README namespace-list gap.** Its argument belongs to
  [`2026-09-01-docs-generation-in-precommit.md`](2026-09-01-docs-generation-in-precommit.md), which
  is open and already makes it.
- **The stale suppression count, the ordering tension between template-first and repo-tasks-first,
  and every verification log.** Acted on, spent, or already in the commits they describe.

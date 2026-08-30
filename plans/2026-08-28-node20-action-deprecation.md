---
status: in-progress
updated: 2026-08-29
depends_on: [scaffoldapy, power-user-linux-setup, agent-skills]
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
here inherits the deprecation at birth. The blast radius grows with each generation, and a generated
repo's owner has no reason to suspect it. This is the same "true of scaffoldapy's own tree, false of
what it generates" shape that
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) records for
`failOnWarnings`.]

### What actually changed across the majors

Read from the upstream release notes rather than assumed, because two of the three are not routine:

- **`checkout@v5.0.0`** (2025-08-11) — the Node 24 move itself. Declares a **minimum runner version
  of v2.327.1**; irrelevant on GitHub-hosted runners, load-bearing for anything self-hosted.
- **`checkout@v6.0.0`** (2025-11-20) — "persist creds to a separate file". This one touches work
  done in this family on 2026-08-26: `persist-credentials: false` was added to every checkout to
  satisfy zizmor's `artipacked`, and `power-user-linux-setup`'s `devcontainer.yml` carries two
  `# zizmor: ignore[artipacked]` suppressions. Whether those suppressions are still needed under
  v6's mechanism is a real question, not a formality.
- **`checkout@v7.0.0`** (2026-06-18) — blocks checking out a fork PR under `pull_request_target` and
  `workflow_run`, plus an ESM rewrite. A genuine behavioural change, though these repos take no fork
  PRs, so the risk here is low and the security default is the one we want anyway.
- **`setup-python@v6.0.0`** (2025-09-04) — explicitly labelled a breaking change: upgrade to
  Node 24.

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

[NEEDS CLARIFICATION: do the two `# zizmor: ignore[artipacked]` suppressions in
`power-user-linux-setup`'s `devcontainer.yml` survive the upgrade, or does v6's separate-credential-
file mechanism make them unnecessary? Worth checking rather than carrying forward — a stale
suppression is exactly the kind of thing that hides a real finding later. The gate will answer it
directly: drop them and see whether `zizmor --offline` still passes.]

### Should a task check this, and fix it?

Raised by the user 2026-08-28, immediately after the plan landed: "shouldn't we have a task to check
whether any of these versions are behind and fix it in our files?" Researched rather than answered
from instinct, because the framing hides two different questions with different best answers.

**The hard constraint first:** currency cannot be a gate step. Answering "is this behind?" requires
asking a remote registry, and `quality.check` is offline and deterministic in every consumer by
design. Anything here is a standalone `@requires(NETWORK)` task, the same shape as the
still-deferred CI `deps.audit` step
([`2026-08-24-devpi-dependency-weight.md`](2026-08-24-devpi-dependency-weight.md)) — which is worth
noting as a sibling: both are network-only currency checks that the gate cannot host, and if either
gets built the other's design should follow it.

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
   across on the assumption they are still needed.
4. **Verify by annotation, not by conclusion.** The whole reason this went unseen is that a green
   run looks identical either way, so the check that closes this plan is re-reading the annotations
   on a post-change run of each repo — `gh api repos/<owner>/<repo>/check-runs/<job-id>/annotations`
   — and confirming the Node 20 message is gone. A passing CI run proves nothing here.

[DEFERRED: the standing-check question in the last open question above is a separate piece of work
with its own trade-offs (Dependabot's PR-per-bump model against this family's direct-to-main
convention), and should not hold up clearing the deprecation itself.]

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

[UNVERIFIED: nothing here has measured how often a major in this family carries a change that
actually reaches these repos. Today's sample is three actions, of which one (setup-uv v10) had a
breaking change worth checking and none had one that bit. A sample of three is not a rate.]

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

Three repos and one template still carry it. All of them are outside this repo, so they join the
batched cross-repo pass already deferred in
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) rather than being done
piecemeal from here:

| repo                     | remaining                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------- |
| `scaffoldapy`            | own CI, **plus `template/.github/workflows/`** — the only site still emitting new instances |
| `power-user-linux-setup` | `checkout`, `setup-python@v5`, and the two `artipacked` suppressions to drop and re-test    |
| `agent-skills`           | `checkout`                                                                                  |

[PITFALL: "do the template first" (direction 1 below) and "repo-tasks first" (what happened) are in
tension, and the tension is real rather than a mistake to correct — the template is the only call
site that keeps producing new instances, so every generation between now and that fix inherits the
deprecation. The mitigation is that no repo is expected to be generated in that window; if one is,
it needs the bump by hand.]

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

[DEFERRED: neither task runs on a schedule, so both still need someone to type them. That is the
same "an opt-in check nobody runs can sit stale indefinitely" trade-off that the integration tier
and the CI `deps.audit` step carry, and it should be settled once for all of them rather than three
times — now [`2026-08-30-scheduled-checks-cadence.md`](2026-08-30-scheduled-checks-cadence.md).
Worth noting that `ci.status` is at least already part of a habit — it is the pre-push check — so
the annotation half is closer to being actually seen than the currency half is.]

[DEFERRED: **SHA-pinning every workflow, plus dependabot to keep the pins fresh.** Only
`publish.yml` is pinned today, by the decision now recorded in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md) — pinning everywhere without
dependabot means pins rot, and dependabot means a recurring PR stream on repos whose owner pushes
straight to `main` and reviews no PRs. Moved here from the retired quality-gate sweep plan because
`ci.check-actions` is the third option that decision did not have: a checker that reports staleness
without opening a PR may make pinning everywhere maintainable by hand after all.]

[DEFERRED: `ci.check-actions` reads the pin's version but never checks that a SHA pin's comment is
_truthful_ — a comment saying `# v7.0.1` beside a SHA that is something else would be reported as
current. `pinact` does verify this. Not a gap worth a Go-binary install method on its own, but worth
knowing the check has a floor.]

[DEFERRED: the README's namespace overview never named `gitflow` either. `ad4b84d` added `ci`
because this session added a task to it; `gitflow` is a pre-existing gap, mentioned in the
release-flow prose further down but absent from the list that claims to enumerate every facility.]

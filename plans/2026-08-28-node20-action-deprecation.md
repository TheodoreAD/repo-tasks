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
in [`2026-08-26-quality-tool-gaps.md`](2026-08-26-quality-tool-gaps.md) §11 and the `unpinned-uses`
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

[NEEDS CLARIFICATION: does this become a shipped concern or stay per-repo? `repo-tasks` already owns
the family's tool list and its shipped configs, but it does **not** own anyone's workflow files —
`configs.pull` distributes `ruff.toml`/`pytest.ini`/`zizmor.yml`, never `.github/workflows/`. So
there is no existing mechanism to push an action bump to consumers, and the honest options are a
hand-edit per repo (four repos, one template, ~16 sites) or accepting that workflows are simply not
part of the shared surface. The latter is probably right and worth stating explicitly, since the
question will recur with the next deprecation.]

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
design. Anything here is a standalone `@requires(NETWORK)` task, the same shape as the deferred §11
`deps.audit` — which is worth noting as a sibling: both are network-only currency checks that the
gate cannot host, and if either gets built the other's design should follow it.

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

[NEEDS CLARIFICATION: A or B, or both? A is cheap, general, and fits an existing task; B actually
edits the files, which is what was asked for. The honest middle is that A would have caught this
issue eleven months earlier at near-zero cost, while B is what fixes it — but B's value is mostly
one-off, since this backlog only accumulated because nothing was watching. Doing A first and seeing
whether B is still wanted is the cheaper order.]

[NEEDS CLARIFICATION: if B, is it Dependabot or a task? Dependabot needs no install at all and is
the conventional answer; the objection is PR-per-bump against direct-to-main. But that objection may
be weaker than it looks — these repos already push through a branch-protection bypass, so a
Dependabot PR is not competing with a review process that exists. Worth pricing honestly before
writing any code.]

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

[UNVERIFIED: that the annotation is actually gone. Nothing here proves it — the gate is offline and
a green run looked identical before, which is the whole point of this plan. The check is
`gh api repos/<owner>/repo-tasks/check-runs/<job-id>/annotations` on the first run after these
commits are pushed, and it cannot be done until they are.]

### Not in scope, but found while here

`astral-sh/setup-uv` is pinned at `v9.0.0` (plain) and `c771a70e…` (hash) across this repo's three
workflows, while current upstream is **`v10.0.1`** (2026-08-14, checked 2026-08-29). That is not a
Node 20 issue — setup-uv was never flagged, and the table above correctly lists it as clean — but it
is the same class of drift, found the same way, and it is evidence for question B above: nothing in
this family notices a major going by. Left alone rather than folded in, because a currency bump with
no deprecation forcing it is a different decision with different risk.

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

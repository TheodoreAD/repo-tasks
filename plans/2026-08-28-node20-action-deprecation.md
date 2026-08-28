---
status: idea
updated: 2026-08-28
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

[NEEDS CLARIFICATION: should the version bump go to `v7` or to `v5`? `v5` is the minimum that clears
the Node 20 warning and carries the least behavioural change; `v7` is current and avoids doing this
again in six months. The `v6` credential change and the `v7` fork-PR block both argue for reading
before jumping, but neither looks risky for these repos specifically. Defaulting to `v7` unless the
`artipacked` interaction below turns up something.]

[NEEDS CLARIFICATION: do the two `# zizmor: ignore[artipacked]` suppressions in
`power-user-linux-setup`'s `devcontainer.yml` survive the upgrade, or does v6's separate-credential-
file mechanism make them unnecessary? Worth checking rather than carrying forward — a stale
suppression is exactly the kind of thing that hides a real finding later. The gate will answer it
directly: drop them and see whether `zizmor --offline` still passes.]

[NEEDS CLARIFICATION: is there a check worth adding so the next deprecation is not found by accident
eleven months late? A green run hid this one completely. Options: have `ci.status` surface
annotations rather than only conclusions (it already parses `gh run list --json`, so annotations are
a second call away); or let `actionlint`/`zizmor` catch outdated actions, which neither does today —
they check syntax and security, not currency. Dependabot is the conventional answer and would open
PRs per repo, which cuts against the family's direct-to-main habit but is worth pricing.]

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

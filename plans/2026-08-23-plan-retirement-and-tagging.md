---
status: landed
updated: 2026-08-23
depends_on: [power-user-linux-setup]
---

## Context

`plans/` has 14 files, of which 5 are `landed` and 1 is `superseded` — none retired. The `plan-docs`
skill's "Retiring a plan" procedure exists but has never been exercised in this repo, and
`contributing/` (the destination it names) doesn't exist yet, so this cleanup also sets that
directory's precedent.

Reading all six retirement candidates end to end surfaced a gap in the skill itself, which is why
this is a plan rather than a chore: **three of the five `landed` plans carry live unfinished work
inside a file the skill says to delete.**

- `plans/2026-08-19-release-management.md:331` — `## Known follow-up`: `version.bump` writes a new
  version via `bump-my-version` but never re-runs `uv lock`, so a bump commit leaves `uv.lock` stale
  ([astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643)). Real, unfixed, tracked
  nowhere else.
- `plans/2026-08-19-docker-image-tasks.md:71` — `### 4. Auth — deferred, not dropped`: the Phase 2
  re-auth-on-401 cycle and the shared `src/repo_tasks/_registry_auth.py` helper.
- `plans/2026-08-20-venv-deps-tasks.md:185` — the §6 multi-stage Docker recipe should get a pointer
  from `dogfood-sample-service.md` once that Dockerfile is written, rather than being written out a
  third time.

The skill already forbids stashing future work in `README.md`/`AGENTS.md`/`docs/` prose, on the
grounds that prose has no status field so nothing ever prompts a return visit. It never applies that
rule to plans themselves — yet a `landed` plan is the same failure mode one level up, and worse,
because the procedure ends in `rm`. Retiring these six as the skill currently reads would silently
drop all three.

Scope also includes the cross-reference cost, which is larger than the skill's step 3 implies: **25
inbound references** point at the six retiring files, 24 from surviving plans and one from code
(`tests/integration/conftest.py`). `release-management.md` alone has 9 inbound. Six simultaneous
deletions means rewiring a citation graph, not fixing a couple of stale links.

### On file size specifically

The prompt for this work was "large files are not so good for LLMs, break them into smaller focused
files." Measured, that premise doesn't hold here: plan files run 59–228 lines, median ~110, with one
outlier (`release-management.md`, 341 lines ≈ 9k tokens). That reads in one shot; splitting it four
ways costs extra round trips and risks an agent reading 1 of 4 and missing a constraint that lived
in another.

[DECISION: split retiring plans by content **lifecycle**, not by byte count. A long file whose
content is all one lifecycle stays one file; a short file mixing four lifecycles gets split. Size is
a symptom, not the criterion.]

The lifecycle classes below came out of actually sorting all six files' content, and they are what
the tag vocabulary in §1 encodes.

| class                | example                                                  | destination                         | survives deletion? |
| -------------------- | -------------------------------------------------------- | ----------------------------------- | ------------------ |
| A — settled decision | bump-my-version over commitizen; devpi over pypiserver   | `contributing/`                     | must               |
| B — pitfall          | devpi's `+simple` URL shape; `127.0.0.1` not `localhost` | `contributing/`                     | must               |
| C — code contract    | task signatures, flag lists, no-op-on-empty behavior     | already in code/tests/README — drop | no                 |
| D — verification log | dry-run rounds 1–4, "both fixtures start and tear down"  | drop, except the unverified residue | no                 |
| E — live open work   | the three items above                                    | an open `plans/*.md`                | must               |

Class C and D are the bulk of the deletable volume: `release-management.md`'s four dry-run rounds
alone are ~55 lines that collapse to a single surviving sentence (`gh pr create` has still never run
against a real GitHub-linked repo — and `plans/2026-08-19-gitflow-test-repo-twin.md` already owns
that).

Prior art was checked before designing §1 rather than after.
[Conventional Comments](https://conventionalcomments.org/) establishes the
closed-label-set-plus-freetext shape (`<label> [decorations]: <subject>`) and the
machine-parseability argument;
[GitHub Spec Kit](https://github.com/github/spec-kit/blob/main/templates/spec-template.md) is where
this skill's existing `[NEEDS CLARIFICATION: ...]` marker comes from, and confirms it is Spec Kit's
_only_ inline semantic marker — there is no upstream vocabulary to adopt wholesale, so extending the
one marker already in use beats importing a parallel scheme.

## Design

### 1. Tag vocabulary — five bracketed markers, one of them already in use

Bracketed SHOUTY-word-plus-colon, matching the existing `[NEEDS CLARIFICATION: ...]` exactly rather
than introducing a second shape. Deliberately _not_ bare `TODO`/`FIXME`/`NOTE`: those collide with
code comments, so `rg TODO` in a repo that also contains source is useless, whereas
`rg '\[PITFALL:'` has effectively zero false positives.

`PITFALL` over `GOTCHA` (too informal for a doc that outlives the session) and over `WARNING`/
`CAUTION` (GitHub markdown alerts already own `[!WARNING]`/`[!CAUTION]`, muddying both the semantics
and the grep). `CAVEAT` was the runner-up, rejected because a caveat qualifies a claim whereas these
entries are traps that were actually fallen into.

| tag                        | means                                                 | retirement action                      |
| -------------------------- | ----------------------------------------------------- | -------------------------------------- |
| `[NEEDS CLARIFICATION: …]` | open question, blocks promotion (existing, unchanged) | must be zero to leave `idea`           |
| `[DECISION: …]`            | settled choice + why it beat the alternatives         | → `contributing/`                      |
| `[PITFALL: …]`             | non-obvious trap, confirmed by hitting it             | → `contributing/`                      |
| `[DEFERRED: …]`            | consciously scoped out, still wanted                  | → an open plan; **blocks deletion**    |
| `[UNVERIFIED: …]`          | designed or implemented but not actually proven       | → verify or defer; **blocks `landed`** |

Five is the whole vocabulary and it should stay that way — a large label set doesn't get applied
consistently, and inconsistent tags are worse than none because they make the greps look
authoritative while being incomplete.

No `[VERIFIED: …]` counterpart, deliberately: verified is the default state of a landed plan, so
tagging it would mark almost every paragraph and destroy the signal. What matters is the _absence_
of `[UNVERIFIED:`, which is negative-space and free to check.

**Granularity rule: tag the claim, not the section.** One tag per discrete, individually-extractable
fact — a tag whose scope is "everything below this heading" can't be migrated mechanically, which is
the entire point.

**Placement rule: a tag opens its own line** — starting a paragraph, or immediately after a list
marker. [PITFALL: found while retrofitting Phase 2. A bare `rg '\[DEFERRED:'` also matches every
prose _mention_ of a tag, so a document that discusses the convention (this one) reports a large
false backlog, and a tag buried mid-paragraph is easy to miss when skimming. Anchoring the pattern —
`rg '^\s*[-*]?\s*\[DEFERRED:'` — drops the false positives to zero, but only works if tags are
consistently written at line start. Verified against this repo: unanchored reports 5 files, anchored
reports the 4 that actually carry deferrals.]

### 2. The two gates this buys

The payoff is that the skill's two hardest judgment calls become greps that either return nothing or
block:

```shell
# promotion gate — must be empty before status leaves `idea`
rg '^\s*[-*]?\s*\[NEEDS CLARIFICATION:' plans/<file>.md

# deletion gate — must be empty before `rm`
rg '^\s*[-*]?\s*\[DEFERRED:|^\s*[-*]?\s*\[UNVERIFIED:' plans/<file>.md

# repo-wide backlog, without opening a single file
rg -c '^\s*[-*]?\s*\[DEFERRED:' plans/
```

The deletion gate is the one that would have caught all three Class E items above. It is a hard
stop, not advice: a plan with a live `[DEFERRED:` is not retireable until that item has been moved
to a plan that stays.

[DECISION: prefer appending a `[DEFERRED:` item to an **existing** open plan that already owns the
concern, over spawning a new plan file. Three extractions here produce two new files, not three —
`venv-deps-tasks.md:185`'s recipe-pointer note belongs on `dogfood-sample-service.md`, which already
owns that Dockerfile.]

### 3. Tags are required at transitions, not while drafting

[PITFALL: a convention that demands discipline on every edit decays, and a half-tagged corpus is
worse than an untagged one — the greps in §2 return clean and get trusted.] Mitigation: tagging is
required only at a status transition (`idea`→`planned`, anything→`landed`, and retirement), never
while drafting freely. Those are exactly the moments someone is already reading the file closely, so
the marginal cost is near zero.

Corollary for this repo: the eight surviving plans get retrofitted as part of Phase 2 below, not
lazily over time. A partial retrofit would poison the repo-wide backlog grep from day one.

### 4. `contributing/` layout — one file per question a reader arrives with

Not one file per retired plan (that just reproduces each plan's own lifecycle mixing under a new
name), and not a byte budget. Four files, derived from the Class A+B inventory:

1. `contributing/release-flow.md` — **how to apply gitflow here**: what each flow does step by step
   (feature / release / hotfix / support / support-hotfix), PR mode vs `local=True`, the two-step
   `*_finish`/`*_finalize` split and why finish can't be synchronous, `sync/<tag>` branches, the
   pitfalls each flow has, and **how to recover from a bad state**. From `release-management.md` §2.
2. `contributing/versioning.md` — **what a version number is here**, strictly: semver, pre-release/
   dev-version conventions, and how a single logical version is expressed across python, docker, and
   helm — which is not one format. Plus the bump mechanism's rationale (bump-my-version over
   commitizen/python-semantic-release, runtime-generated per-group config), tag-name schemes, and
   the uv#15643 interaction. From `release-management.md` Context + §1.
3. `contributing/test-tiers.md` — the unit / opt-in integration / clean-OS tier split, devpi-server
   over pypiserver (PEP 691 coverage), `registry:3` via testcontainers, the `127.0.0.1`-not-
   `localhost` pitfall, skip-don't-fail posture. From `local-index-and-registry-testing.md`, joined
   later by `clean-os-integration-testing.md` (itself since retired into that file too).
4. `contributing/task-module-conventions.md` — echo every command; no-op cleanly on an absent
   artifact kind; never silently mutate (`--locked`, never `--frozen`, never bare `uv sync`);
   single-writer rules (`deps.lock` owns `uv.lock`, `version.py` owns the version field); named
   flags over an opaque `ci=True`; the `_next_steps()` "print what to run next" rule.

[DECISION: `release-flow.md` and `versioning.md` stay two files, not one. They are one workflow but
answer two different questions, and the split is a clean cut by subject rather than by workflow
stage: versioning owns **the number** (what format, per artifact kind), release-flow owns **the
procedure** (what to run, in what order, and what to do when it goes wrong). Neither needs the other
open to be useful — someone adding a Helm chart reads only the first, someone whose release branch
is stuck reads only the second.]

File 4 is the highest-value one and exists as a unit in **none** of the plans — it is scattered
across five of them. That is the concrete argument for organizing by reader-question rather than by
source file, and it is also why this can't be done mechanically.

#### These four files start incomplete, and that gets tracked

Migration can only carry across what the six retiring plans actually contain, which is less than the
scopes above describe. The gaps are real and known now, so they get their own plan rather than being
discovered later as silence:

- `versioning.md` — **pre-release/dev-version conventions are undocumented anywhere in this repo**,
  and the python-vs-docker-vs-helm question has a genuine conflict behind it that no plan has ever
  addressed: python uses PEP 440 (`1.0.0rc1`, `1.0.0.dev1`), while Helm chart versions must be
  strict SemVer 2 (`1.0.0-rc1`) and Docker tags forbid `+` outright, so semver build metadata can't
  round trip. One logical version, three incompatible spellings, and `version.py` currently assumes
  they agree.
- `release-flow.md` — **recovery procedures don't exist**. The plans record that bad states happen
  (the hotfix-into-release-branch merge conflict is documented as an accepted rough edge) but never
  how to get out of one. Also missing: aborting a release branch, a tag pushed to the wrong commit,
  `*_finalize` run before the PR actually merged, a `sync/<tag>` PR closed without merging.
- `test-tiers.md` — thinnest gap; mostly needed the clean-OS tier folded in once
  `clean-os-integration-testing.md` (now retired) landed its first real mutating test — done
  2026-08-23.
- `task-module-conventions.md` — assembled from five sources, so it needs a coherence pass rather
  than new facts.

These go in `plans/2026-08-23-contributing-docs-completion.md` (`status: idea`), not as
`[DEFERRED:]` tags inside the `contributing/` files themselves — prose docs describe what is true
now, and the whole point of the tag vocabulary is that unfinished work lives in something with a
status field. The `contributing/` files simply stay silent on what they don't yet cover, rather than
carrying "TODO: document recovery" lines that nothing would ever prompt a return to.

Split of concern against `AGENTS.md`: `AGENTS.md` states the rule ("one module per facility"),
`contributing/` states why and what was rejected. `AGENTS.md`'s existing Conventions section gains
pointers, not content.

### 5. Skill enhancement — only after the pilot

Per `~/AGENTS.md`'s "Pilot before generalizing", the `plan-docs` skill is edited **last**, from
whatever survived contact with the six real files — not first, from this design. Expected edits:

- The tag vocabulary (§1) and the two gates (§2), as a new section.
- A new hard rule in "Retiring a plan": a plan carrying live unfinished work is not deletable until
  that work is moved to a plan that stays. This is the existing "Don't stash future work in prose
  docs" rule, applied to plans themselves.
- Step 3's reference-fixing guidance strengthened: grep inbound references _before_ starting, since
  the count (25 here) determines whether retirement is one commit or several.
- The lifecycle table from Context, as the triage aid for what migrates versus what gets dropped.
- The size/lifecycle distinction, stated explicitly so "this file is long" doesn't get read as
  "therefore split it."

## Files touched

Phase 1 — extract live work (own commit, before any deletion):

- `plans/2026-08-23-uv-lock-on-version-bump.md` (new, `status: idea`) — from
  `release-management.md:331`.
- `plans/2026-08-23-registry-auth-retry.md` (new, `status: idea`) — from `docker-image-tasks.md` §4,
  also referenced by `helm-chart-tasks.md:46`.
- `plans/2026-08-19-dogfood-sample-service.md` — gains the multi-stage-recipe pointer from
  `venv-deps-tasks.md:185`.

Phase 2 — retrofit tags on the eight surviving plans (own commit).

Phase 3 — write destinations (own commit, before any deletion):

- `contributing/release-flow.md`, `contributing/versioning.md`, `contributing/test-tiers.md`,
  `contributing/task-module-conventions.md` (all new).
- `plans/2026-08-23-contributing-docs-completion.md` (new, `status: idea`) — the known gaps in the
  four files above, per §4.
- `AGENTS.md` — a new "Where things are written down" section pointing at `contributing/` and at the
  tag greps, plus a trim of the Conventions section now that its rationale lives in
  `contributing/task-module-conventions.md`.
- `README.md` — no change needed after all. It has no directory-structure section to extend; its
  only `plans/` mentions are inside a URL to another repo.

Phase 4 — add `## Migrated to` to all six retiring plans (own commit — **must land before the
deletion commit**, or the section never appears in git history at all).

Phase 5 — rewire the 25 inbound references, then delete (own commit):

- 24 references across the 8 surviving plans, repointed at `contributing/*.md` or dropped.
- `tests/integration/conftest.py` — one reference to `local-index-and-registry-testing.md`, repoint
  to `contributing/test-tiers.md`.
- Delete the six retiring plan files.

Phase 6 — the skill itself (own commit, in a different repo). The skill is **authored in
`power-user-linux-setup/skills/plan-docs/`** and installed to `~/.agents/skills/` by `inv ai.skills`
— `~/.claude/skills` is a symlink to that install directory, not the source. Edit the source repo.

[PITFALL: a skill edit does not reach the installed copy until `inv ai.skills` is re-run, so
`~/.agents/skills/<name>/` stays stale in the meantime — and a Claude Code session loads the
_installed_ copy, not the source. Refresh just the edited one with `inv ai.skills --skill=<name> -y`
— the `--skill` flag was added for exactly this (power-user-linux-setup `2f67630`). The one case it
will not touch is content whose `.pulse-source` marker is missing or points elsewhere, which it
treats as foreign and leaves alone even with `-y` — deliberately, since that marker is the ownership
model and a flag overriding it would make ownership mean two different things.]

## Verification

- The §2 deletion gate returns empty for each of the six, immediately before its deletion — the gate
  applied to its own pilot.
- A whole-repo grep for the six filenames (not just `plans/`, per the skill's rule) returns **no
  live pointers**. It does not return zero hits, and demanding zero would be wrong: two kinds of
  mention legitimately survive a deletion, and conflating them with dangling links causes real
  damage.
  - **Provenance**, which must stay but must be marked: "extracted from the now-retired
    `plans/X.md`". A reader needs to know where something came from; they also need to know not to
    go looking for it. Every one of these carries "now-retired" or equivalent.
  - **This plan's own record** of what it retired, including the line numbers it cited as evidence.
    Rewriting those would destroy the record of why the work was necessary.
  - Anything else — a bare path presented as somewhere to go read more — is a dangling link and must
    be repointed or dropped.
- Every reference that cited a _specific section title_ (e.g. `release-management.md` Design §2)
  points at a heading that actually exists in the new destination, not merely a valid file path.
- `inv quality.precommit` passes after each phase — dprint reflows markdown at `lineWidth: 100`, and
  a many-file docs pass is exactly the change that trips it.
- Spot-check the reverse direction: for each of the four `contributing/` files, confirm a reader
  arriving with that file's question finds the answer without needing a deleted plan.

[UNVERIFIED: the claim that Class C content is fully redundant with code/tests/README rests on
reading, not on a mechanical check. Before deleting each plan, confirm its Class C claims actually
appear in `src/repo_tasks/*.py` docstrings or `README.md` — a task flag documented _only_ in a plan
would be silently lost.]

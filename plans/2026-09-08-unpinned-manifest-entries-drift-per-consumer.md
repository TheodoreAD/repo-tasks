---
status: idea
updated: 2026-09-08
source_repo: github.com-personal/scaffoldapy
source_session: 7a3f34e6-b0c7-4532-8c89-ec43239414e7.jsonl
source_moment: 2026-09-07T21:20:00Z
---

# An unpinned manifest entry means every consumer holds a different version, and nothing says so

## Context

`repo-tasks-quality` is an exported manifest, and one of its entries carries no version at all:

```toml
"invoke-stubs @ git+https://github.com/TheodoreAD/invoke-stubs",
```

`configs.ensure-deps` splices that string into each consumer's own `dependency-groups.dev`, and each
consumer then resolves it **at its own lock time** and freezes. So the manifest names a package, not
a version, and the version actually in effect is per-consumer lock state that nothing here can see
or report.

Measured 2026-09-07/08: `repo-tasks` moved from `ad052ca` (0.1.0) to `9ec1974` (0.2.0) to `1c3bbeb`
(0.3.0) over one day. `scaffoldapy` was still locked at `ad052ca` — the distribution's **first**
commit, frozen when `configs.ensure-deps` first put the entry there on 2026-08-25. Two repos, one
manifest line, two versions, twelve days apart. A freshly _generated_ repo, meanwhile, resolves
whatever `main` holds at generation time, so it is on a third value again — confirmed the same day:
ten rendered repos all installed `f70ff01` (0.3.0) while the repo that generated them held 0.1.0.

**This is a sibling of the drift this plan's own item 2 closed, not the same one.**
[`2026-08-25-consumer-transitions.md`](2026-08-25-consumer-transitions.md) added dev-group drift to
`configs.diff` (`e169837`, 2026-08-26), which catches an entry a consumer is **missing**. An entry
that is present but locked three versions back is invisible to it, by construction — `ensure_deps`'
own docstring says so:

> Additive only: never touches an entry already present (by bare package name, ignoring version) …
> this task never touches `uv.lock` itself.

So `configs.diff` says "up to date" about a consumer whose stubs predate two releases, and that is
the correct answer to the question it asks. Nobody is wrong; there is just no question being asked
about locked versions.

**What actually surfaced it** was not any check. A session in this repo bumped the stubs, noticed
`scaffoldapy` would be behind, and filed a plan by hand — which worked, and does not scale past the
person who happens to remember.

## Evidence

`scaffoldapy` session `7a3f34e6-b0c7-4532-8c89-ec43239414e7.jsonl` under
`~/.claude/projects/-home-tdumitrescu-projects-github-com-personal-scaffoldapy/`, 2026-09-07. The
user's own words, which is what turned a routine bump into this question:

> shouldn't invoke stubs be already baked into repo-tasks?

It is baked in — that was the answer — and the follow-up is what this plan is for: baked in as a
_name_, with the version left to each consumer.

The repro needs no session:

```shell
rg -n invoke-stubs <consumer>/uv.lock     # the rev that consumer froze
rg -n invoke-stubs pyproject.toml         # the manifest entry, no rev
inv configs.diff                          # in that consumer: silent about the gap
```

## Open questions

[NEEDS CLARIFICATION: pin the rev in the manifest, or keep it unpinned and detect the drift? Pinning
(`@ git+…@f70ff01`) makes this repo the single version authority: a bump is one edit here, and every
consumer moves when it re-runs `configs.ensure-deps` — but `ensure-deps` is additive and ignores
version, so it would have to learn to _update_ an entry it already placed, which is a real change to
a task whose whole contract today is that it never disturbs an existing line. Detecting instead
keeps consumers free to resolve on their own schedule and adds a report, which is the shape
`ci.check-actions` already took for a structurally identical question: currency needs the network,
so it cannot be a gate step.]

[NEEDS CLARIFICATION: is this specific to the one git-sourced entry, or does it generalise? Every
other entry in `repo-tasks-quality` is a PyPI name, mostly unversioned, so the same argument applies
to all of them — a consumer locked to an eight-month-old `ruff` is the same failure with a slower
clock and a louder eventual symptom. The git entry is merely where it shows first, because its
"latest" moves on a personal timetable and its releases carry no version anyone reads. Deciding this
for `invoke-stubs` alone would be answering the instance rather than the class.]

[NEEDS CLARIFICATION: if detection, where does it live and what does it read? `configs.diff` is the
natural home — it is already the "are you behind the family" command and consumers already run it in
the sweep — but it is offline today, and answering "is this lock behind" for a git dependency means
asking GitHub for the branch head, and for a PyPI one means asking the index. That would give
`configs.diff` a network mode, or split a `deps.check-currency` off beside `deps.audit`, which is
already network-only and report-only for a related question.]

[NEEDS CLARIFICATION: does the answer change once this repo tags a release?
`2026-08-25-consumer-transitions.md` item 5 leaves tagging open, and `bootstrap-repo-tasks.sh` is
unpinned until a real tag exists. A tagged `repo-tasks` gives consumers a version to pin _to the
tool_, but the manifest entries are still names inside it — so this question survives tagging rather
than being answered by it. Worth confirming that reading before deferring anything to the release.]

## Recommended direction

Rough, and deliberately not settled — the class question above comes first, because answering it for
`invoke-stubs` alone builds the wrong mechanism.

If the answer is **detect**, the precedent is right here: `ci.check-actions` reports staleness,
exits zero, edits nothing, and reaches every consumer through the tool rather than through a file.
The argument that settled it there transfers whole — an auto-bumping mechanism performs the cheap
half and hands over a diff whose risk is unread, while a detector automates the part that gets
forgotten and leaves the judgement to whoever is reading.

If the answer is **pin**, the cost lands on `configs.ensure-deps`, whose additive-only contract is
load-bearing today (it is what makes the sweep safe to re-run), and the sweep in
`contributing/consumer-sweep.md` grows a step. Worth pricing that against how often a manifest entry
actually needs to move in lockstep — for `invoke-stubs`, twice so far, both this month.

Either way the near-term action is the same and does not need this decided: when an entry in
`repo-tasks-quality` moves in a way consumers should take, say so in the sweep rather than trusting
someone to notice.

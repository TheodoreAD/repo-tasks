---
status: idea
updated: 2026-09-04
---

# What a version number means here, and cutting the first real release

## Context

Raised by the user 2026-09-04: dogfood releasing in this repo, since this repo is the mechanism the
rest of the family will use for it. Stay on `0.X.Y` until the package is fully developed, and **do
not spend effort deciding whether a change is breaking** — the family is evolving quickly and
changing course often, so that analysis is waste. The user's own default was minors only, `0.X.0` →
`0.(X+1).0`, with a stated reservation that it may look strange to consumers later.

The immediate motivation is concrete rather than tidiness. Consumers now pin this repo's reusable
security workflow by SHA (`contributing/quality-gate.md`), and `ci.check-actions` reports a stale
pin by asking `gh api repos/<owner>/<repo>/releases/latest`. With no releases that query returns
nothing, the pin is skipped as "nobody's release to track", and a pinned consumer goes stale
silently. **A release here is what turns that guard on.**

## What is actually true today, checked 2026-09-04

- **This repo has never released anything.** `git tag --list` is empty. The rc cycle has only ever
  been exercised against a local bare repo standing in for `origin`.
- **There is no `develop` branch** — `main` only, locally and on the remote. So `gitflow`'s
  canonical flow (branch `release/X.Y.Z` off `develop`, PR into `main`, tag, sync back) has no base
  to start from here without inventing one.
- **Nothing anywhere runs `gh release`.** `version.bump` commits and tags (`vX.Y.Z`, `tag=True` by
  default), and a tag is not a release: `releases/latest` stays empty. Tagging alone does not switch
  the currency check on.
- **`power-user-linux-setup` has a `stable` tag**, currently on a commit a few behind its `master`.
  It is a single _moving_ tag marking last-known-good, carries no version, and is the low-ceremony
  convention the user was thinking of.

[PITFALL: a git tag and a GitHub Release are different objects, and only the second answers
`releases/latest`. `inv version.bump minor` produces the tag and stops, so a release flow that ends
there looks complete, pushes a real `v0.2.0`, and leaves every pinned consumer exactly as unwatched
as before. This is the trap most likely to make the first release feel like it worked while
delivering none of the reason for cutting it.]

## The proposal: derive minor-vs-patch from the shipped surface, not from breakage

The user is right that breaking-change analysis is waste here, and SemVer agrees: under `0.x`
anything may change at any time, so nothing is being violated by not doing it. That frees
minor-vs-patch to carry a **different and more useful signal**, and this package happens to have an
unusually crisp one available.

**The enumeration, audited 2026-09-04.** The first pass listed four surfaces from reading
`configs.py`; the audit found thirteen. Three kinds, and the middle group is the one the first pass
missed almost entirely — this package writes far more into a consumer's repo than the config files.

**A. Files this package writes into a consumer's repo**

| what                                                                                          | written by                       |
| --------------------------------------------------------------------------------------------- | -------------------------------- |
| `ruff.toml`, `pyrightconfig.json`, `dprint.json`, `pytest.ini`, `zizmor.yml`, `.editorconfig` | `configs.pull` (`_CONFIG_FILES`) |
| `pyproject.toml` — the `repo-tasks-quality` entries spliced into `dependency-groups.dev`      | `configs.ensure-deps`            |
| `tasks.py`                                                                                    | `configs.py`                     |
| `bootstrap-repo-tasks.sh` — pins the `repo-tasks` version the repo installs                   | `configure`, via `selfinstall`   |
| `.python-version`                                                                             | `venv.py`                        |
| `.claude/settings.json`, and the `CLAUDE_ENV_FILE` it names                                   | `agents.py`                      |

**B. Contracts a consumer authors or depends on by name**

| what                                                                    | why it is a contract                                                                                 |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `repo-tasks.toml` schema — `[[docker]]`, `[[helm]]` entries             | the consumer writes this file; a schema change breaks theirs                                         |
| the `repo-tasks-quality` group's contents                               | what lands in their `pyproject.toml` and their lock                                                  |
| `inv` task names                                                        | cited in their docs, CI, Dockerfiles                                                                 |
| `from repo_tasks import ns`                                             | the documented default in every consumer's `tasks.py`                                                |
| every task module importable by name (`from repo_tasks import quality`) | `__init__.py` documents this for consumers hand-picking a subset, so **module names are API**        |
| `configure` staying unnested                                            | `__init__.py`: "the one command anything outside this package should ever need to depend on by name" |
| `bootstrap.sh`                                                          | what a consumer and their CI run before anything else                                                |

**C. Called by other repos**

`.github/workflows/security-reusable.yml`.

So:

- **minor (`0.X.0`)** — any surface above moved. "Pulling this will change something in your repo."
- **patch (`0.X.Y`)** — none of them did. "Upgrading is a no-op for you; it is internals, docs,
  tests or a fix behind an unchanged surface."

Why this beats the two obvious alternatives:

- **Against minors-only**: it answers the question a consumer actually has, which is not "will this
  break me" but "do I need to run `configs.pull` and read a diff". With minors-only every release
  looks like it might touch their repo, so the number stops being information.
- **Against SemVer breakage semantics**: it needs no judgement at all. "Did any of these things
  change" is a `git diff --name-only <last tag>..HEAD` over a path list, plus a comparison of task
  names and of the importable module set — mechanically checkable, and therefore enforceable by a
  task rather than by remembering.
- **It does not look strange later.** At 1.0 exactly one rule is added — breaking goes to major —
  and minor and patch keep the meanings consumers already learned. Nothing has to be re-explained.

[DECISION: **adopted by the user 2026-09-04.** Minor and patch here mean "the shipped surface moved"
and "it did not", never SemVer's breaking and non-breaking. That has to be stated wherever a
consumer meets it, because the parts look like SemVer's and mean something else — the difference is
not visible from the number.]

[PITFALL: **the first enumeration was wrong by a factor of three, and wrong in the direction that
would have made the rule useless.** It listed the config files, the dependency group, the task names
and the reusable workflow — and missed that `configure` stamps `bootstrap-repo-tasks.sh` into the
consumer's repo, that `venv.py` writes `.python-version`, that `agents.py` writes
`.claude/settings.json`, that `repo-tasks.toml`'s schema is a file consumers author, and that
`__init__.py` documents every task module as importable, which makes **module names** API. A rule
enforced against an under-counted surface reports "patch" for a release that rewrites a file in
every consumer repo, which is worse than no rule: it would be trusted.]

[DECISION: the honest one-line test, now that the list is known, is **"would a consumer's repo look
different, or would any file they wrote stop working?"** Everything in A and B follows from it, and
it is what a future addition should be checked against rather than the list being maintained by
memory.]

The practical consequence is worth stating plainly: with thirteen surfaces rather than four,
**minors will be common and patches rarer than the first pass implied.** That is not a flaw in the
rule — a release that rewrites `.python-version` in every consumer repo genuinely is a minor — but
it does mean patch means something quite narrow here: internals, tests, docs, plans, and fixes
behind an unchanged surface. Which is exactly the set of changes a consumer can upgrade through
without looking.

[DEFERRED: **a task that computes the part for you.** `inv version.next-part --since v0.2.0` diffing
the surfaces above and printing `minor` or `patch` is the natural end state, and it is exactly the
kind of thing this package exists to hand other repos. Not needed for the first release — the answer
for a first release is trivially "whatever we call it" — and designing it before the rule has been
used once would be the wrong order.]

## Open questions

**Answered 2026-09-04, in the plan that owns it** —
`plans/2026-08-25-release-without-release-branch.md`. Both shapes ship: the canonical gitflow one is
untouched, and a trunk shape is added beside it in its own namespace. This repo will use the trunk
one, since it has no `develop`. What is still open there is the namespace's name.

## Is the tag push manual? Researched 2026-09-04, and it changes the design

The question: is pushing a tag normally a human act or an automated one? The answer is unambiguous
and it is **both, in a specific order — the tag push is the manual gate, and everything downstream
automates off it.**

Read from the projects' own workflow files via the GitHub API, not from a search summary:

| project         | publish trigger                                                           |
| --------------- | ------------------------------------------------------------------------- |
| `psf/requests`  | `push: tags: ["v*"]` plus `workflow_dispatch` with a test-pypi-only input |
| `pallets/flask` | `push: tags: ["*"]`                                                       |
| `encode/httpx`  | `push: tags: ["*"]`                                                       |
| `astral-sh/uv`  | `workflow_call`, driven by a release-orchestration workflow               |

PyPA's own guide agrees on the mechanism — `on: push` with
`if: startsWith(github.ref,
'refs/tags/')` — and instructs the reader to "push a tagged commit" to
trigger publication. Nowhere is the tag itself created by automation: it is the human's deliberate
act, and it is the _only_ one.

[PITFALL: **this repo already implements that convention, and the new `trunkflow.cut` walks into
it.** `publish.yml` fires on `push: tags: v[0-9]+.[0-9]+.[0-9]+`, and its TestPyPI job is
unconditional — the real-index job sits behind the `pypi` environment's reviewer rule, TestPyPI does
not. So `inv trunkflow.cut --bump minor`, which pushes the tag, does not mean "bump the version": it
means "upload to TestPyPI and queue a PyPI approval". A command whose name and help text describe a
version bump should not have publication as a side effect. Found by reading `publish.yml` while
answering this question, not by the tests, which mock every `c.run`.]

[PITFALL: and today that side effect **fails**. The trusted-publisher registration is a one-time
manual setup on TestPyPI and PyPI that has never been done — it is the open blocker on
`plans/2026-08-22-pypi-publish-integration.md`. So the first `trunkflow.cut` would push a tag, fire
`publish.yml`, and go red on a repo that has just been told its release flow works.]

A false alarm worth recording so nobody re-finds it: `docker-release.yml` looked like it triggered
on `release:`, which would have coupled `release.create` to an image push too. It does not — that
`release:` is the **job name**; the workflow is `workflow_dispatch` only. Grepping `^  release:` in
a workflow finds both, and they mean opposite things.

[NEEDS CLARIFICATION: should `trunkflow.cut` stop before pushing? The convention above says the tag
push is the gate, which argues for `cut` doing the local bump and tag and then printing the push
command together with what it will trigger — one deliberate step, matching what every project
surveyed treats as the moment of decision. It also matches this package's own `gitflow`, where
`release_start` bumps with `tag=False` and the tag only lands at finalize. Against: it is one more
command in a flow whose entire purpose is low ceremony. A middle option is `--push` defaulting to
false.]

## Releasing is manual, and the task is the primitive

[DECISION: **a release is never automatic**, per the user 2026-09-04 — not every version merits one,
and a version that does may not want it immediately. So nothing tag-triggered: no workflow that
fires because a `v*` tag appeared. Both entry points are deliberate acts.]

[DECISION: **a task, with a `workflow_dispatch` workflow calling it** — not two implementations of
the same thing. The task is the primitive because an agent can run it and because it is testable the
way every other task here is; the workflow exists so a human can cut a release from GitHub's UI
without a checkout. The workflow bootstraps and runs the task.]

That is the opposite call from `security-reusable.yml`, which deliberately runs `uv audit --locked`
raw rather than `inv deps.audit`, and the two are consistent once the reason is named:

|                          | security workflow        | release workflow                                       |
| ------------------------ | ------------------------ | ------------------------------------------------------ |
| logic behind the command | none — one uv subcommand | resolving the tag, refusing a duplicate release, notes |
| how often it runs        | every push to `main`     | rarely, by hand                                        |
| bootstrap cost           | dominates a 0.7s job     | irrelevant                                             |

So the rule is not "always avoid `inv` in CI" — it is that a workflow duplicates a command only when
the command has no logic worth single-sourcing and the bootstrap would dominate. Here both are the
other way round, and duplicating `gh release create` plus its guards in YAML is exactly the drift
the audit workflow's own test exists to prevent.

### The task

`inv dist.create-release [--tag vX.Y.Z]`, defaulting to the most recent tag.

[DECISION: **not `dist`.** The first proposal was `dist.create-release`, on the reasoning that
`dist` owns artifacts leaving the repo. The user questioned whether `dist` is scoped only to Python
artifacts, and it is — checked 2026-09-04, its own docstring reads "Python distribution
build/publish/query tasks (build a wheel, publish it, list a project's published versions)", and all
four of its tasks are `uv build`, `uv publish`, a clean of `dist/`, and a PEP 691 index query. A
GitHub Release is a **repo-level event**: it may reference wheels, or a Docker image, or a Helm
chart, or no artifact at all. Filing it under `dist` would assert that a release of this repo is a
Python package, which is one of the things consumers ship rather than what a release is.]

[PITFALL: do not name it `dist.release` either, and not only for the scoping. That is noun-only,
which the naming rule forbids, and it would read as a sibling of
`gitflow.release-start`/`release-finish`/`release-candidate` — a different concept in a different
flow. `dist.publish` is taken and means "upload to a package index", so reusing `publish` here would
give one verb two targets.]

[NEEDS CLARIFICATION: where does it go instead? It is wanted by **both** flows — gitflow's
`release-finalize` tags `main`, the trunk shape tags `main` directly, and either may then want a
GitHub Release from that tag. So it belongs to neither branching model exclusively, which rules out
both `gitflow` and the new trunk namespace. `version.py` is the closest existing home, since it
already creates the tag, but its docstring scopes it to version _strings_ and their three spellings,
and a Release is a GitHub object carrying notes rather than a version string. A small module owning
the release _event_, shared by both flows, is what the rest of this package's structure would
suggest — and it is bound up with the namespace question below.]

A `--tag` argument rather than always taking `HEAD`'s tag is what makes "release later, or never"
work: a tag can sit unreleased indefinitely and be released when someone decides it should be.

[NEEDS CLARIFICATION: does `repo-tasks` want a moving `stable` tag as well? It is a different
mechanism for a different question — `stable` says "what should I install", version tags say "what
am I pinned to" — so they are complementary rather than alternatives. Probably not needed here,
since consumers pin SHAs and the currency check reads releases, but it is the convention the user
named and worth ruling in or out deliberately.]

## Is a release needed now? No — checked, and the urgency was overstated

The case for cutting one immediately was that SHA-pinned consumers go unwatched while
`releases/latest` is empty. **Checked 2026-09-04: there are no SHA-pinned consumers.** The only
caller of `security-reusable.yml` anywhere is this repo's own `security.yml`, which uses the
relative `./` form and carries no ref at all. So the currency check has nothing to watch either way,
and releasing today would improve nothing that exists.

[DECISION: the release waits for the mechanism, not the other way round. Cutting `v0.2.0` by hand
now — `git tag` plus a `gh release create` typed at a prompt — would be the one thing this exercise
is not for: the point is to dogfood the flow other repos will use, and a hand-cut release is
evidence about nothing. Build `dist.create-release` and the trunk release shape first, then use
them.]

The release does become necessary the moment the first external caller pins a SHA, which is the
`scaffoldapy` template plan. That is the real trigger to watch.

## Recommended direction

In order, each step being the prerequisite of the next:

1. **Settle the surface enumeration** (the `UNVERIFIED` tag above). The rule is only as good as the
   list, and it is cheap to get right before anything is written into `contributing/`.
2. **Decide the release shape** — `plans/2026-08-25-release-without-release-branch.md`, now that the
   user has said both shapes are wanted rather than one replacing the other.
3. **Build `dist.create-release`**, plus the `workflow_dispatch` workflow that calls it.
4. **Cut `v0.2.0` with them.** It is a minor under the adopted rule whichever way the enumeration
   settles: surfaces 1, 2 and 4 have all moved since `0.1.0` was set — the packaged-tests configs,
   the ruff `banned-api` entry, `pytest-timeout` in the manifest, and the reusable workflow itself.
5. **Write the policy into `contributing/release-flow.md`**, stating plainly that minor and patch
   here mean "surface moved" and "surface did not", not SemVer's breaking and non-breaking.
6. Let that release be the evidence `2026-08-25-release-without-release-branch.md` has been waiting
   for, and close its question with what happened rather than with a prediction.

# Versioning

What a version number is in this repo, who is allowed to write one, and how a single logical version
is expressed across a python package, a docker image, and a helm chart. For the branch/PR mechanics
that surround a release, see [`release-flow.md`](release-flow.md).

## Scheme: semver, bumped explicitly

`major.minor.patch`, and the part is **always an explicit argument** — never inferred from commit
messages. That is the load-bearing decision, not an incidental one: automatic inference is what
creates the gitflow problems described under "Tool choice" below, and not depending on it avoids
them entirely rather than working around them.

## Grouping: what bumps together

Versions are per-_group_, not per-repo and not strictly per-project:

- A python project is its own group by default (`group == name`).
- A docker image and the Helm chart that wraps **that specific image** share one `group` and bump
  together, because a chart's `appVersion` is meaningless independent of the image it deploys.
- Anything with no `group` key is its own independent group.

`version.py` bumps and tags one group at a time. An unrelated shared library elsewhere in the repo
keeps its own version, untouched by that release. Group membership is resolved from
`projects.py`/`repo-tasks.toml` at call time.

**A group's version lives in a python project's `pyproject.toml`.** `_resolve_project` matches a
group name against a discovered python project, so every group needs one — a docker image and chart
grouped under a name no python project answers to cannot resolve `current_version` at all, and
`docker.build`/`helm.push`/`version.bump` all fail on it. `tests/fixtures/sample-service` is the
shape that works: the workspace member, the `[[docker]]` entry, and the `[[helm]]` entry all carry
the same name, so the member's `[project].version` is the group's single source of truth. A
chart-only or image-only group would need a version source this model doesn't have yet.

[PITFALL: `Chart.yaml`'s formatting is load-bearing, and nothing in the repo's own quality gate
protects it. The generated bump config searches for an unquoted `version:` and a quoted
`appVersion:` as literal strings, so a YAML formatter (or an editor set to normalize quotes) that
rewrites either one turns the next group bump into a hard failure. `dprint.json` excludes
`**/templates/*.yaml` because Go templates aren't parseable YAML at all — `Chart.yaml` itself is
still formatted, and was checked to come back byte-identical. `tests/integration/`'s dogfood module
pins both shapes against the real file so a future formatter change fails a test rather than a
release.]

[PITFALL: `helm package` re-serializes `Chart.yaml` through its own YAML marshaller on the way into
the `.tgz` — comments are dropped and `appVersion` comes back unquoted. The archive's copy is
therefore not the file the bump searches; never assert the source formatting against a packaged
chart.]

Tag names follow from the group:

- `vX.Y.Z` when the group is the repo's sole implicit project.
- `<group>-vX.Y.Z` once multiple groups exist, matching commitizen's documented monorepo tag-format
  precedent (confirmed working via bump-my-version's own `tag_name` templating, not just
  commitizen's).

## One version, three spellings

A single logical version is **not one string** across the three artifact kinds this repo releases.
The parts are the source of truth — `version.py`'s `Version`: `major.minor.patch`, an optional `rc`
number, and for dev builds only a `dev` distance and `commit` — and each kind renders them its own
way:

| artifact     | spelling                                                                                       | written by                              |
| ------------ | ---------------------------------------------------------------------------------------------- | --------------------------------------- |
| python       | PEP 440 in `pyproject.toml`/`uv.lock`: `1.1.0`, `1.1.0rc2`, `1.0.1.dev3+g1a2b3c`               | `version.py`                            |
| helm chart   | SemVer 2 in `Chart.yaml`'s `version` **and** `appVersion`: `1.1.0-rc.2`, `1.0.1-dev.3.g1a2b3c` | `version.py`, as part of the group bump |
| docker image | the SemVer spelling as the tag: `1.1.0-rc.2`, `1.0.1-dev.3.g1a2b3c`                            | `docker.py`, from `Version.semver()`    |

Nothing translates one string into another. `pyproject.toml`'s PEP 440 form is what
`current_version` returns; `docker.py`/`helm.py` parse it back to parts and ask for `semver()`, and
`dist.py` uses it as-is. The three spellings are the lossless subset of PEP 440 ↔ SemVer (one
pre-release segment, one dev segment) — `post`, epochs, and alpha/beta are rejected by
`Version.parse` by name, because no file in a repo on these tasks should ever hold one.

Three constraints shaped the spellings, all verified 2026-08-25:

- A Docker tag is `[\w][\w.-]{0,127}` — no `+`, so SemVer build metadata cannot round-trip into an
  image tag. The commit hash of a dev build therefore rides _inside_ the pre-release identifiers
  (`-dev.3.g1a2b3c`), and the chart uses the same spelling so `appVersion` equals the image tag.
- PyPI rejects local versions (`+g1a2b3c`) outright, while a private index generally accepts them —
  exactly the split a dev build wants. `dist.publish` refuses a dev build without a named index.
- Ordering agrees where it matters: `dev.N < rc.N < final` in both schemes.

Pre-releases are opt-in for every consumer by each ecosystem's own rules — pip/uv skip them unless
asked, `helm install` skips them without `--devel`, and `docker.release` never tags an rc or dev
build `latest`.

### The rc cycle

`release_start` bumps to `X.Y.0rc1`; `gitflow.release-candidate` bumps `rcN` → `rcN+1` and tags
`vX.Y.0rcN+1` on the release branch; `release_finish` drops the rc (`X.Y.0`) before the branch
merges. The branch is named after the final version throughout, and that is the tag `main` receives.
A hotfix goes straight to its final version by default (`--rc` opts into the cycle); a support patch
always does. See [`release-flow.md`](release-flow.md#the-release-candidate-cycle).

In bump-my-version terms the scheme is two extra parts, `pre_l` (`rc` | `final`, `final` optional so
it serializes to nothing) and `pre_n` (first value `1`), with `serialize` overridden per
`Chart.yaml` file entry to the SemVer form — the generated config carries all of it.

[PITFALL: with `pre_l` in the scheme, _every_ `major`/`minor`/`patch` bump lands on `rc1` —
`bump patch` from `1.1.0` gives `1.1.1rc1`, never `1.1.1` (confirmed against bump-my-version 1.5.1).
The straight-to-final path (`bump --no-rc`, what a hotfix uses) states the version outright with
`--new-version` instead of relying on the part arithmetic; two bumps (`patch` then `pre_l`) would
make two commits.]

### Dev builds

`version.set-dev` (behind `dist.build --dev`, `docker.build --dev`, `helm.package --dev`) writes a
git-derived version into the working tree — `pyproject.toml`, `uv.lock`, every chart in the group —
and never commits: the next patch of the nearest final tag (or the next candidate of a nearest rc
tag), then the commit distance and short hash. It refuses a dirty tree, so the undo is always the
`git restore` it prints; a CI checkout is clean by construction.

[DECISION: a working-tree write, not dynamic versioning (`hatch-vcs`/`uv-dynamic-versioning`). The
build backend deriving the version at build time would take the field away from `version.py`'s
single-writer ownership, cannot write `Chart.yaml`, and would leave `uv.lock` embedding a value the
backend no longer owns. (2026-08-25)]

[DECISION: [dunamai](https://github.com/mtkennerly/dunamai) computes the git-derived parts (`base`,
`stage`, `revision`, `distance`, `commit`) rather than a hand-rolled `git describe` parser; the
serializers are ours. dunamai's own SemVer style spells the bumped stage `-pre.N`, not `-dev.N`, and
its metadata has no `g` prefix — and a static `--format` cannot express "stage present or absent"
(`{base}-{stage}.{revision}.dev.{distance}` renders `1.0.1-..dev.2` when there is none). So the
API's parts feed `Version`, never a dunamai format string. (2026-08-25)]

[PITFALL: a dev version has no bump-my-version spelling — its `parse` would reject the `.devN+g…`
tail — so `set_dev` applies the same search/replace pairs the generated config is built from
directly, in Python. The file entries are kept as data (`_FileEntry`) for exactly that reason: one
file set, rendered two ways, so a chart or lock entry can never drift between the two paths.]

## Single writer

`version.py` is the only module that writes a version field anywhere. `dist.py` reads whatever is
already in `pyproject.toml` and never writes it; `docker.py` reads it via
`current_version(c, group=image.group)` to resolve a tag, and `helm.py` does the same to name the
packaged `.tgz` it pushes. Two modules racing to touch the same value is the failure this avoids —
the same single-writer posture `deps.lock` has over `uv.lock`
([`task-module-conventions.md`](task-module-conventions.md#single-writer-rules)).

## Tool choice: bump-my-version

All three candidates were installed and driven against a throwaway repo simulating the docker+helm
group-bump case (a `pyproject.toml` version plus a paired `chart/Chart.yaml`'s `version`/
`appVersion`) — not compared from documentation.

**`bump-my-version` — chosen.** Config-driven, no conventional-commit requirement, no inference: the
caller states the bump. Closest fit to classic gitflow, where a release manager _decides_ the bump
at `release start` time rather than deriving it after the fact.

**`commitizen` — close second, a legitimate fallback.** It also satisfied every hard requirement
(explicit bump, multi-file group bump in one commit+tag, configurable tag template,
independent-group isolation). This was not a blowout. bump-my-version wins on two counts: it has no
commit-message-inference code path _at all_, so it is structurally impossible to regress into a
surprise inferred bump; and its 9-package dependency footprint doesn't drag in changelog/
conventional-commit machinery this repo has deliberately deferred. Worth revisiting if CHANGELOG
generation is ever added — its default substring-replace bumped both `Chart.yaml` keys with zero
per-file regex, genuinely simpler there.

**`python-semantic-release` — rejected, on hands-on evidence rather than the abstract "fights
gitflow" argument.** It does have real explicit-override flags (`--major`/`--minor`/`--patch`), so
the common "it only infers" criticism is imprecise. The actual blockers:

1. `semantic-release version --minor --no-push --no-vcs-release` fails outright with
   `error: No such remote 'origin'` on a repo with no configured remote — directly conflicts with
   this repo's local-only-by-default finish tasks.
2. `--minor` on a fresh repo with no prior release tag **silently no-ops** — prints
   `The next version is: 0.1.0!` (unchanged) and tags `v0.1.0` with no bump and no commit. Only a
   second run, after a prior tag existed, bumped correctly.

The override flags force the bump _type_ but don't bypass the release-history parsing engine, and
the very first release is a silent-no-op trap. Its open gitflow issues
([#789](https://github.com/python-semantic-release/python-semantic-release/issues/789),
[#1215](https://github.com/python-semantic-release/python-semantic-release/issues/1215)) point the
same way.

## The config is generated per bump, never static

`version.py` writes a **temporary `.bumpversion.toml` at call time** (`--config-file <tmp>`), built
from that call's resolved group members, and deletes it afterward. Two reasons, the first confirmed
by hitting it:

[PITFALL: bump-my-version's pure-CLI mode (`--no-configured-files` + positional file args + one
global `--search`/`--replace`) **cannot express different search/replace templates per file in one
call**. Confirmed by `Did not find 'version = "0.2.0"' in file: 'chart/Chart.yaml'` when a
TOML-style pattern was applied to the YAML file.]

A static hand-authored `.bumpversion.toml` doesn't work either: a group's file set — which projects
and charts belong to it — isn't fixed, only resolved at call time.

The tag name is set inside the generated config (`tag_name`), not via a CLI flag. `tag = true`
becomes conditional on the `tag` keyword argument, because `gitflow.py`'s `release_start`/
`hotfix_start` pass `tag=False` — the tag belongs on `main` at finish time, not on the branch at
bump time.

### Why `next_version` is hand-rolled

`next_version(current, part, rc=True)` is plain arithmetic with no subprocess, rather than shelling
out to `bump-my-version show --increment`. `gitflow.py` needs it to name a release/hotfix branch
_before_ the bump commit exists. The generated config does customize `parse`/`serialize` (the rc
scheme above), so the arithmetic is not safe by construction the way it was for bare `X.Y.Z` — it is
safe because `tests/integration/test_version_integration.py` drives every transition
(`major`/`minor`/`patch` → `rc1`, `rc` → `rc+1`, `final`) through
`bump-my-version show new_version --increment <part>` on the very config `version.py` generates and
asserts equality before each real bump. A scheme divergence fails a test, not a release. The actual
file-writing and committing stays 100% owned by bump-my-version.

[DECISION: keep the hand-rolled copy and pin it, rather than shell out from `gitflow.py`. The pin is
what makes it safe; a subprocess at branch-naming time would add one more `c.run` to mock in every
gitflow test for no correctness gain once the pin exists. (2026-08-25)]

## `uv.lock` moves with the bump

`uv.lock` embeds the project's own version, and
[astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643) means `uv sync --locked` fails
when only that version changed. A bump that left the lock alone would commit a stale one, surfacing
later as a confusing `venv.sync` failure on a tree that looks clean — and `venv.py` passes
`--locked` everywhere precisely so staleness fails loudly, so the discipline that keeps the repo
safe is what turns this into a first-release-day trap.

[DECISION: the generated bump config carries a `uv.lock` file entry, so bump-my-version rewrites the
version there in the same commit it already owns. The obvious alternative — run `deps.lock` after
the bump — lands the lock in a _second_ commit, because bump-my-version makes the commit itself
(`commit = true`); taking commit construction away from it (`commit = false`, `version.py` doing the
`git add`/`git commit`) was rejected as undoing a deliberate part of the tool choice. Only the
workspace root's `uv.lock` is touched: a member has no lock of its own, its version sits in the root
one. A repo with no `uv.lock` gets no entry and no hook.]

[PITFALL: `uv.lock` spells the project's own version exactly like every dependency's — a bare
`version = "X"` inside a `[[package]]` block — so a bare search would also hit any dependency pinned
at the same number. The entry is anchored on the `name = "<project>"` line uv writes immediately
before `version`, which is unique per package. That is a multi-line search, so the generated TOML
spells it as a basic (double-quoted) string — a single-quoted TOML string is literal and would hand
bump-my-version a backslash and an `n`.]

The generated config also sets `pre_commit_hooks = ["uv lock --check"]`, so the rewrite is verified
by uv itself before anything is committed: if the anchored search ever misfires, the bump fails
instead of shipping a stale lock. Measured: a text-rewritten version passes both `uv lock --check`
and `uv sync --locked`, and `tests/integration/test_version_integration.py` pins that against a real
`uv lock` for a single project and for a workspace member. This is not a second writer of
`uv.lock`'s resolution — `deps.lock` still owns every dependency in the file — see
[`task-module-conventions.md`](task-module-conventions.md#single-writer-rules).

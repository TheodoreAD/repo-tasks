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

Tag names follow from the group:

- `vX.Y.Z` when the group is the repo's sole implicit project.
- `<group>-vX.Y.Z` once multiple groups exist, matching commitizen's documented monorepo tag-format
  precedent (confirmed working via bump-my-version's own `tag_name` templating, not just
  commitizen's).

## One version, three formats

A single logical version is **not one string** across the three artifact kinds this repo releases:

| artifact     | format                                                  | written by                                     |
| ------------ | ------------------------------------------------------- | ---------------------------------------------- |
| python       | PEP 440, in `pyproject.toml`'s `[project].version`      | `version.py`                                   |
| docker image | tag on the image ref                                    | `docker.py`, from the resolved group's version |
| helm chart   | SemVer 2, `Chart.yaml`'s `version` **and** `appVersion` | `version.py`, as part of the group bump        |

For plain `X.Y.Z` releases all three agree, which is why the current implementation gets away with
treating them as one string. They diverge as soon as pre-release versions enter the picture — PEP
440 spells a release candidate `1.0.0rc1` while SemVer 2 requires `1.0.0-rc1`, and Docker tags
forbid `+` outright so SemVer build metadata cannot round-trip.

**This repo has no pre-release/dev-version convention yet, and `version.py` currently assumes the
three formats agree.** Tracked in `plans/2026-08-23-contributing-docs-completion.md`.

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

`next_version(current, part)` is plain arithmetic with no subprocess, rather than shelling out to
`bump-my-version show --increment`. Safe specifically because the config `version.py` generates
never customizes bump-my-version's `parse`/`serialize` — every version this repo bumps is the tool's
own default `major.minor.patch` scheme, so there is no scheme this could diverge from. The actual
file-writing and committing stays 100% owned by bump-my-version.

If a future change ever customizes `parse`/`serialize` (a pre-release scheme would), this assumption
breaks and `next_version` must change with it.

## Known interaction: `uv.lock` goes stale on bump

`uv.lock` embeds the project's own version, and
[astral-sh/uv#15643](https://github.com/astral-sh/uv/issues/15643) means `uv sync --locked` fails
when only that version changed. `version.bump` does not re-run `uv lock`, so a bump commit leaves
the lock stale — surfacing later as a confusing `venv.sync` failure on a tree that looks clean.

Unfixed. Tracked in `plans/2026-08-23-uv-lock-on-version-bump.md`, which also records why the
obvious fix doesn't work: bump-my-version owns the commit (`commit = true`), so a later re-lock
lands in a _second_ commit.

---
status: planned
updated: 2026-08-25
---

# Pre-release versions: dev and rc builds across python, docker and helm

## Context

`X.Y.Z`-only releases are a deliberate limitation today
([`contributing/versioning.md`](../contributing/versioning.md), "One version, three formats"), and
the reason is that the three artifact kinds spell a pre-release differently: PEP 440 wants
`1.1.0rc1` / `1.1.0.dev3`, Helm's `Chart.yaml` `version` must be SemVer 2 (`1.1.0-rc.1`), and a
Docker tag is `[\w][\w.-]{0,127}` — no `+`, so SemVer build metadata can never round-trip into an
image tag. `version.py` assumes all three agree, `docker.py`/`helm.py` reuse `current_version` as-is
for the tag and the `.tgz` name, and `next_version` is plain arithmetic that only knows
`major.minor.patch`.

Enterprise work needs two kinds of pre-release artifact, and they are different problems:

- **rc builds** — a release candidate cut from the release branch, deployed to staging, iterated
  (`rc1`, `rc2`, ...) and promoted to the final version without a rebuild of the _version scheme_.
  These are deliberate, human-triggered, and committed: a real version in `pyproject.toml`, a real
  tag.
- **dev builds** — every merge to `develop` (or any branch CI builds) produces an installable,
  deployable artifact whose version says where it came from. These are automatic, never committed,
  and must never collide with anything a human will later release.

Extracted from `plans/2026-08-23-contributing-docs-completion.md` (now retired) once the direction
was settled 2026-08-25: solve it properly rather than restrict to `X.Y.Z`. The three open questions
were answered the same day; decisions are inline below.

### What the three formats allow (verified 2026-08-25)

| kind       | pre-release                 | build/commit info                                              | resolver behavior                                             |
| ---------- | --------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------- |
| PEP 440    | `1.1.0rc1`, `1.1.0.dev3`    | local version `+g1a2b3c` — **rejected by PyPI**, fine on devpi | pre-releases skipped unless requested or nothing else matches |
| SemVer 2   | `1.1.0-rc.1`, `1.1.0-dev.3` | `+g1a2b3c` (ignored for precedence)                            | Helm skips pre-release charts unless `--devel`                |
| Docker tag | `1.1.0-rc.1`, `1.1.0-dev.3` | must ride inside the tag: `1.1.0-dev.3.g1a2b3c`                | none — `latest` is whatever was tagged last                   |

The lossless subset (python-semver's documented conversion table, PEP 440 §"Semantic versioning"):
`major.minor.patch`, one pre-release segment (`rc`/`a`/`b` ↔ `-rc.N`), one dev segment (`.devN` ↔
`-dev.N`). `post` and `epoch` have no SemVer form and are out of scope; SemVer build metadata has no
PEP 440 form other than a local version, which PyPI rejects.

Ordering agrees where it matters: `dev.N < rc.N < final` in both schemes (`d` < `r` under SemVer's
ASCII comparison; PEP 440 orders dev before pre before final by definition).

Prior art checked 2026-08-25: bump-my-version docs (parts/`optional_value`/`serialize`,
`show --increment` needs no files), python-semver's PEP 440 ↔ SemVer conversion notes, dunamai's
README, Helm chart docs (`version` SemVer 2 including pre-release/build metadata; `appVersion`
free-form, quote it), distribution/reference's tag grammar.

## Design

One logical version with **parts** as the source of truth — `major`, `minor`, `patch`, `pre_l` (`rc`
| final), `pre_n` — and each artifact kind gets its own serialization of the same parts. No
translation between strings, only parts → string per kind. The stored PEP 440 form in
`pyproject.toml` stays canonical (`packaging` normalizes `1.1.0-rc.1` to `1.1.0rc1` anyway).

### 1. `version.py` — parts model, per-kind serializers, rc-aware bump config

- A small frozen `Version` (parts above, plus optional `dev: int` and `commit: str` that only a dev
  build sets) with `parse(pep440: str)` accepting `X.Y.Z` and `X.Y.ZrcN` only — anything else (`a`,
  `b`, `.dev`, `.post`, local) is a `ValueError` naming the accepted shapes, since a committed
  version is never one of those; and two serializers, `pep440()` and `semver()`. Docker uses
  `semver()` unchanged: the rc form has no `+`, and dev builds (§3) put the hash inside the
  pre-release identifiers.
- The generated bump config gains a global `parse` regex for the two accepted shapes,
  `serialize = ["{major}.{minor}.{patch}{pre_l}{pre_n}", "{major}.{minor}.{patch}"]` for
  `pyproject.toml` and the `uv.lock` entry, a per-file
  `serialize = ["{major}.{minor}.{patch}-{pre_l}.{pre_n}", "{major}.{minor}.{patch}"]` on both
  `Chart.yaml` entries, and `[tool.bumpversion.parts.pre_l] values = ["rc", "final"]`
  `optional_value = "final"`. bump-my-version 1.5.1 documents per-file `parse`/`serialize` overrides
  (howto "custom version formats by file").
- `next_version(current, part)` extends to `part in {"major", "minor", "patch", "rc", "final"}`:
  `major`/`minor`/`patch` reset to `rc1` when the caller asks for a pre-release start (see §2's
  `_start`), `rc` increments `pre_n`, `final` drops the pre-release. It stays pure arithmetic.
- [DECISION: `next_version` stays hand-rolled, pinned by a test that drives every transition through
  `bump-my-version show new_version --increment <part> --current-version X --config-file <the same
  generated config>`
  (no files needed for `show`) so a scheme divergence fails a unit test rather than a release.
  Shelling out from `gitflow.py` would add a subprocess at branch-naming time for no correctness
  gain once the pin exists — the pin is what makes the hand-rolled copy safe, exactly the argument
  `versioning.md` already makes for the `X.Y.Z` case. (2026-08-25)]
- Verified 2026-08-25 against a throwaway repo (bump-my-version 1.5.1, temporary `--config-file`
  regenerated per step, `pyproject.toml` + `chart/Chart.yaml` with the two per-file `serialize`
  lists above, `parts.pre_n.first_value = "1"`): `bump minor` → `1.1.0rc1` / `version: 1.1.0-rc.1` /
  `appVersion: "1.1.0-rc.1"`; `bump pre_n` → `rc2`, `rc3`; `bump pre_l` → `1.1.0` / `1.1.0` in all
  three fields; one commit per step; and `show new_version --increment <part>` printed the same
  value before every bump. The `parse` regex is
  `(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:(?P<pre_l>rc)(?P<pre_n>\d+))?`.
- [PITFALL: with `pre_l` in the scheme, _every_ `major`/`minor`/`patch` bump lands on `rc1` —
  `bump patch` from `1.1.0` gives `1.1.1rc1`, never `1.1.1` (confirmed in the spike). The
  straight-to-final hotfix path therefore passes `--new-version <next_version(..., final)>` to
  `bump-my-version bump` instead of relying on the part arithmetic; `_bump` grows a `new_version`
  argument for it. Two bumps (`patch` then `pre_l`) would make two commits.]

### 2. `gitflow.py` — the rc cycle lives on the release branch

- [DECISION: `release_start --bump minor` bumps to `X.Y.0rc1` on `release/X.Y.0` (branch named after
  the final version, as today); a new `gitflow.release-candidate` bumps `rc` (`rcN` → `rcN+1`), tags
  `vX.Y.0rcN+1` on the release branch and pushes the tag, so the tag-triggered workflows build
  staging artifacts; `release_finish` bumps `final` (`X.Y.0`) as its first step and then opens the
  PR into main as today. Hotfixes go straight to final by default — `hotfix_start` produces `X.Y.Z`,
  and an rc cycle on a hotfix is opt-in via `--rc`, which routes it through the same
  `release-candidate` task. This is nvie's canonical shape; the tag on the release branch is the
  only addition. (2026-08-25)]
- The `_require_tag_absent` guard checks the final tag as today; `release-candidate` checks its own
  rc tag before tagging.
- Teams that do not want a release branch for every release are a separate design —
  `plans/2026-08-25-release-without-release-branch.md`.

### 3. Dev builds — computed from git, written to the working tree, never committed

- [DECISION: a `version.set-dev` task (with `dist.build --dev`, `docker.build --dev`,
  `helm.package --dev` calling it first) computes the dev version from git and writes it into
  `pyproject.toml`, `uv.lock` and every group `Chart.yaml` in place — the same bump-my-version
  config with `--new-version <dev> --no-commit --no-tag`, so `version.py` stays the single writer
  and the lock stays consistent. Locally the task refuses on a dirty tree and prints the
  `git restore` that undoes it; in CI the checkout is throwaway. Dynamic versioning
  (`hatch-vcs`/`uv-dynamic-versioning`) was rejected: it takes the field away from `version.py`,
  cannot write `Chart.yaml`, and `uv.lock` would embed a value the backend no longer owns.
  (2026-08-25)]
- The dev version is [dunamai](https://github.com/mtkennerly/dunamai)'s scheme (MIT, zero
  dependencies): `Version.from_git()` then `.bump()` — base = next patch of the last reachable final
  tag (or the next `rc` of a reachable rc tag), plus distance and short hash. Our `Version` model
  takes dunamai's _parts_ (`base`, `stage`, `revision`, `distance`, `commit`) and serializes them
  itself: PEP 440 `1.0.1.dev5+g1a2b3c` / `1.1.0rc2.dev1+g81b8701`, SemVer and Docker
  `1.0.1-dev.5.g1a2b3c` / `1.1.0-rc.2.dev.1.g81b8701`. Sorts before any rc or final of the same base
  regardless of whether the next real release turns out to be a patch or a minor. Added to
  `[project].dependencies`.
- Verified 2026-08-25 (dunamai via `uvx`, scratch repo with `v1.0.0` and `v1.1.0rc1`): at distance 3
  from a final tag `--bump` gives PEP 440 `1.0.1.dev3+677e52e` and SemVer `1.0.1-pre.3+677e52e`;
  exactly at a tag, `1.0.0` in both; past an rc tag, `1.1.0rc2.dev1+81b8701` /
  `1.1.0-rc.2.pre.1+81b8701`.
- [PITFALL: dunamai's own SemVer style spells the bumped stage `-pre.N`, not `-dev.N`, and its
  metadata has no `g` prefix — neither is what the docker tag should say. A static `--format` fixes
  the final-tag case (`{base}-dev.{distance}.g{commit}` → `1.0.1-dev.3.g677e52e`) but cannot express
  "stage present or absent": `{base}-{stage}.{revision}.dev.{distance}.g{commit}` renders
  `1.0.1-..dev.2.g99f1e31` when there is no stage. So the serializers are ours, fed by the API's
  parts — never a dunamai format string.]

### 4. Pre-releases are opt-in for every consumer, by each ecosystem's own rules

- `docker.release` tags `latest` only for a final version; `helm install` skips pre-release charts
  without `--devel`; `uv`/`pip` skip them unless pinned or pre-releases are allowed.
- `dist.publish` refuses a `.dev` version against an index that is not `explicit = true` — PyPI
  rejects local versions outright, and the task should say so before `uv publish` does.
- `publish.yml`/`docker-release.yml` see rc tags (they are in the `v*` namespace); both gate
  `latest` and the real-PyPI job on "is final". The `<group>-vX.Y.Z` monorepo tag scheme
  ([`versioning.md`](../contributing/versioning.md)) is orthogonal and stays deferred.

### 5. `contributing/versioning.md`

"One version, three formats" and "Why `next_version` is hand-rolled" are rewritten when this lands —
the assumption they document is exactly what changes. `release-flow.md` gains the rc cycle.

## Files touched

- `src/repo_tasks/version.py` — `Version`, `parse`/`pep440`/`semver`, rc-aware `next_version`,
  rc-aware generated config, `set_dev`.
- `src/repo_tasks/gitflow.py` — `release_start` → rc1, `release_candidate`, `release_finish` →
  final, `hotfix_start --rc`.
- `src/repo_tasks/docker.py`, `helm.py`, `dist.py` — `semver()` for tags/`.tgz` names, `--dev`,
  `latest` and publish gating.
- `.github/workflows/publish.yml`, `docker-release.yml` — final-only gating.
- `pyproject.toml` — `dunamai`.
- `tests/unit/test_version.py`, `test_gitflow.py`, `test_docker.py`, `test_helm.py`, `test_dist.py`;
  `tests/integration/test_version_integration.py` — the `show --increment` pin and the real
  bump-my-version run over a throwaway repo with a chart.
- `contributing/versioning.md`, `release-flow.md`.

## Verification

- Unit: every `next_version` transition equals `bump-my-version show new_version --increment` on the
  same generated config; `semver()` output for `1.1.0rc1` and `1.1.0` matches what `helm lint` and
  `docker tag` accept.
- Integration: a real bump `1.0.0 → 1.1.0rc1 → 1.1.0rc2 → 1.1.0` over a throwaway repo with a
  `Chart.yaml`, asserting the four file forms after each step and that `uv lock --check` passes.
- Integration: `version.set-dev` on a tag-at-distance repo writes the expected PEP 440 and SemVer
  forms and refuses on a dirty tree.
- The dogfood `sample-service` group goes through one full rc cycle in local mode.

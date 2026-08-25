---
status: idea
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
was settled 2026-08-25: solve it properly rather than restrict to `X.Y.Z`.

## What the three formats allow (verified 2026-08-25)

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

## Open questions

[NEEDS CLARIFICATION: where does the rc cycle live in the gitflow? Proposed: `release_start` bumps
to `X.Y.0rc1` on the release branch (branch still named `release/X.Y.0`); a new
`gitflow.release-candidate` bumps `pre_n` (`rc1` → `rc2`), tags `vX.Y.0rc2` on the release branch
and pushes the tag so CI builds rc artifacts; `release_finish` bumps `pre_l` to final (`X.Y.0`)
before opening the PR into main. Hotfixes go straight to final by default — an rc cycle on a hotfix
is the exception, opt-in via the same task. Confirm the hotfix default.]

[NEEDS CLARIFICATION: dev builds need the version written into `pyproject.toml` for `uv build` to
see it, but must never be committed. Proposed: `dist.build --dev` (or `version.set-dev`, a working
tree write with no commit) computes the version from git, writes it, builds, and leaves the tree
dirty-by-design in CI (a throwaway checkout) — versus switching the project to dynamic versioning
(`hatch-vcs`/`uv-dynamic-versioning`), which would take the version field away from `version.py`'s
single-writer ownership and out of `uv.lock`. Which shape?]

[NEEDS CLARIFICATION: does `next_version` keep its pure-arithmetic form, extended to the
`pre_l`/`pre_n` parts and pinned by a test against
`bump-my-version show new_version --increment
<part>` for every transition — or shell out to `show`
(no files needed, only `current_version` + `parse`/`serialize`) and drop the hand-rolled copy?
`gitflow.py` needs it to name the branch before the bump exists; a subprocess there is one more
`c.run` to mock, not a real cost.]

## Recommended direction

Rough. One logical version with **parts** as the source of truth — `major`, `minor`, `patch`,
`pre_l` (`rc` | final), `pre_n` — and each artifact kind gets its own serialization of the same
parts. No translation between strings, only parts → string per kind.

1. **rc releases are bump-my-version's job, per-file `serialize`.** bump-my-version 1.5.1 supports a
   file entry overriding `parse`/`serialize` (howto "custom version formats by file"), so the
   generated config gains a global `parse` accepting `X.Y.Z` and `X.Y.ZrcN`,
   `serialize =
   ["{major}.{minor}.{patch}{pre_l}{pre_n}", "{major}.{minor}.{patch}"]` for
   `pyproject.toml` and `uv.lock`, and
   `["{major}.{minor}.{patch}-{pre_l}.{pre_n}", "{major}.{minor}.{patch}"]` on the two `Chart.yaml`
   entries; `[tool.bumpversion.parts.pre_l] values = ["rc", "final"]
   optional_value = "final"`.
   The stored PEP 440 form stays canonical (`packaging` normalizes `1.1.0-rc.1` to `1.1.0rc1`
   anyway). `next_version`/`current_version` grow a tiny parser for the PEP 440 form and
   `docker.py`/`helm.py` call a `semver(version)` serializer instead of using the string raw —
   `docker.build` tags `1.1.0-rc.1`, `helm.push` looks for `<chart>-1.1.0-rc.1.tgz`. [UNVERIFIED:
   per-file `serialize` with a parts table works from the temporary generated config exactly as from
   a static one — drive it against a throwaway repo before building on it, the way the tool choice
   itself was verified.]
2. **dev builds are computed from git, never bumped.** Base = the next patch of the last reachable
   tag, distance and short hash appended: PEP 440 `1.0.1.dev5+g1a2b3c`, SemVer/Docker
   `1.0.1-dev.5.g1a2b3c`. That is [dunamai](https://github.com/mtkennerly/dunamai)'s documented
   scheme (`Version.from_git()`, `serialize(style=Style.Pep440 | Style.SemVer, format=...)`, zero
   dependencies) — prefer it over hand-rolling `git describe` parsing; `--bump` gives the next-patch
   framing and `format=` gives the docker shape with the hash inside the pre-release identifiers.
   Sorts correctly regardless of whether the next real release turns out to be a patch or a minor.
   [UNVERIFIED: dunamai's exact SemVer output for a final tag at distance N with `bump` — confirm it
   is `1.0.1-dev.N+gSHA` and not `-pre.N`, then pin it in a test.]
3. **Pre-releases are opt-in for every consumer, by each ecosystem's own rules.** rc and dev
   versions never receive `latest` in `docker.release`; `helm install` skips them without `--devel`;
   `uv`/`pip` skip them unless pinned or pre-releases are allowed. Dev builds publish only to
   internal indexes (devpi, GHCR) — PyPI rejects local versions outright, which is the right
   guardrail. `dist.publish` refuses a `.dev` version against an index that is not
   `explicit = true`.
4. **Tags.** rc tags on the release branch (`vX.Y.0rc1`) are real tags in the `v*` namespace, so
   `publish.yml`/`docker-release.yml` triggers see them; the workflows must gate `latest` and the
   real-PyPI job on "is final". The `<group>-vX.Y.Z` monorepo tag scheme
   ([`versioning.md`](../contributing/versioning.md)) is orthogonal and stays deferred.
5. `contributing/versioning.md`'s "Why `next_version` is hand-rolled" and "One version, three
   formats" are rewritten when this lands — the assumption they document is exactly what changes.

Prior art checked 2026-08-25: bump-my-version docs (parts/`optional_value`/`serialize`,
`show
--increment` needs no files), python-semver's PEP 440 ↔ SemVer conversion notes, dunamai's
README, Helm chart docs (`version` SemVer 2 including pre-release/build metadata; `appVersion`
free-form, quote it), distribution/reference's tag grammar.

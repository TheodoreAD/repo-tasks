---
status: landed
updated: 2026-08-24
---

## Context

`docker.py` (`build`/`push`/`release`) has landed and, since 2026-08-23, is exercised against a real
(local) registry by `examples/sample-service` — the dogfood sample whose plan has now retired. What
remains here is the _external_ GHCR half: auth, the CI workflow, and confirming a real push lands
where it should. The image to push for real now exists, so nothing blocks that.

Depends on the routine, every-commit-safe registry testing tier (`registry:3` via `testcontainers`),
per [`contributing/test-tiers.md`](../contributing/test-tiers.md) — that covers what gets exercised
on every `inv test.unit`. This plan covers the real, external GHCR instead: deliberate, occasional,
manual/CI-triggered, not run automatically.

## Design

### 1. Registry choice: GHCR, not Docker Hub

GHCR (`ghcr.io`) is clearly easier for a GitHub-hosted repo: CI auth is just the already-issued
`GITHUB_TOKEN` (`permissions: packages: write` on the workflow) — no separate account, no PAT to
create/rotate/store as a repo secret. Docker Hub would need its own account plus an access token
managed entirely outside GitHub's existing trust boundary, for no offsetting benefit here.
`repo-tasks.toml`'s own `[[docker]]` entry already uses a `ghcr.io/...` image name, so this is also
just confirming the design's existing default rather than introducing a new decision. GHCR packages
default to the same visibility as their owning repo (private stays private) but can be flipped
public per-package via GitHub's UI later if wider distribution is ever wanted — a one-time manual
step, not something `inv`/CI configures.

[PITFALL: GHCR rejects uppercase characters anywhere in an image ref — confirmed by the smoke test
(2026-08-23). This account's GitHub username is `TheodoreAD` (mixed case), so any image name derived
from it — CI's `${{ github.repository_owner }}`, or a future `repo-tasks.toml`
`[[docker]]`/`[[helm]]` entry — must lowercase that segment explicitly
(`docker-registry-smoke-test.yml`'s `${OWNER,,}` step does this for CI). `repo-tasks.toml`'s own
`[[docker]]` entry carries the same note where it actually bites, since that is where the real
`image =` value lives.]

### 2. `docker.py` itself needs zero changes

Image name/registry/Dockerfile/path already come entirely from `projects.discover_docker_images(c)`
(landed) — either an explicit `repo-tasks.toml` `[[docker]]` entry or the zero-config
root-`Dockerfile` default. This plan is purely about the auth/CI/account wiring around whatever
entry exists — `image = "ghcr.io/theodoread/sample-service"`, as `repo-tasks.toml` now has it — not
a `docker.py` design change.

### 3. CI auth: `docker/login-action`, zero new secrets

The standard, documented GHCR-from-GitHub-Actions pattern:

```yaml
- uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
```

`docker.py`'s own Design §4 (landed, deferred) auth-retry-on-401 logic stays irrelevant for this CI
path specifically — `GITHUB_TOKEN` doesn't expire mid-job, and `docker/login-action` runs once up
front. That retry logic remains meaningful only for a human's local/interactive session hitting a
stale credential, not CI.

### 4. Local/manual auth

`docker login ghcr.io -u <github-username>` with a GitHub Personal Access Token scoped to
`write:packages` (classic PAT — GHCR's fine-grained-PAT support should be re-checked at
implementation time, since GitHub has been expanding fine-grained scopes over time) — a one-time
manual step for a human publishing from their own machine, never stored in this repo.

### 5. CI workflow

`.github/workflows/docker-release.yml` (landed 2026-08-24), `workflow_dispatch`-only with a
`project` input defaulting to `sample-service`, running `inv docker.release` after
`docker/login-action`. Kept separate from `publish.yml` rather than merged as a second job: the two
release different artifacts on different cadences, and a docker push is not gated by the PyPI
environment rule.

[DECISION: no tag-push trigger yet. The plan's original "same `vX.Y.Z` tag push as the PyPI
workflow" is wrong for this image — `v*` tags name the root `repo-tasks` project's version, while
the image is versioned by the `sample-service` group, whose tag scheme (`<group>-vX.Y.Z`, per
`contributing/versioning.md`) `version.py` does not emit yet (`tag_name = "v{new_version}"` is
hardcoded). Add the trigger once that exists; until then the workflow is dispatched by hand, which
matches its deliberate/occasional posture anyway.]

### 6. Verification order

1. **Done (2026-08-23):** auth-only smoke test, via
   `.github/workflows/docker-registry-smoke-test.yml` (`workflow_dispatch`-triggered, not wired into
   the regular CI trigger). Confirmed `docker/login-action` + `GITHUB_TOKEN` authenticates against
   `ghcr.io` and pushes `ghcr.io/theodoread/repo-tasks-scratch:smoke-test`
   (`sha256:c766679d161d4ffe3dc4503b4c9f90b978f0d363fcedb02d1ae0cd271e645c0a`) — run
   https://github.com/TheodoreAD/repo-tasks/actions/runs/32631113222.
2. **Done (2026-08-24):** real `inv docker.release --project sample-service` end-to-end in CI
   against GHCR — run https://github.com/TheodoreAD/repo-tasks/actions/runs/32762887843, pushing
   `ghcr.io/theodoread/sample-service:0.1.0` and `:latest`
   (`sha256:e76b928d20cd3ae32bab373c23568cc2162fe96db3ccbefa21ade25fc6f962e0`).
3. **Done (2026-08-24):** the package exists under the expected name; `docker manifest inspect`
   resolves it from a logged-in client. Visibility is **private**: an anonymous
   `GET https://ghcr.io/v2/theodoread/sample-service/tags/list` answers 401.

[PITFALL: a new GHCR package is private by default even when the publishing repo is public — §1's
"same visibility as the owning repo" was wrong. Nothing in the workflow or `GITHUB_TOKEN` controls
this; making it public is a one-time manual flip in the package's settings on github.com, and only
matters once something outside the account needs to pull it.]

## Files touched

- (Done) `.github/workflows/docker-release.yml`. Passes `inv quality.workflow-check` (actionlint)
  and an `inv test.workflows --event workflow_dispatch --job release --dry-run` plan under act.
- (Done) `repo-tasks.toml` — the real `[[docker]]` entry, landed with the dogfood sample rather than
  by this plan. Its `image` is already the GHCR ref this plan pushes to.
- The cross-references from the now-retired `plans/2026-08-19-dogfood-sample-service.md` and
  `plans/2026-08-19-docker-image-tasks.md` went away with those plans; `docker.py`'s design
  rationale now lives in
  [`contributing/task-module-conventions.md`](../contributing/task-module-conventions.md).

## Verification

All three steps of §6 done — the auth smoke test on 2026-08-23, the real release and the package
check on 2026-08-24. Nothing left unverified.

## Migrated to

- [`contributing/release-workflows.md`](../contributing/release-workflows.md) (new): the GHCR-over-
  Docker-Hub decision and its `GITHUB_TOKEN` auth (§1, §3), the lowercase-owner pitfall (§1), the
  private-by-default pitfall (§6), the no-tag-trigger decision (§5), and how to check a workflow
  locally before dispatching it.
- `.github/workflows/docker-release.yml`'s own header carries the dispatch-only posture, and
  `repo-tasks.toml`'s `[[docker]]` comment the lowercase rule where it bites — both already there.
- Not migrated: §2 ("`docker.py` needs zero changes") is a statement about code that is true by
  reading `docker.py`; §4's local `docker login` recipe is GHCR's own documentation; §6's run URLs
  and digests are a verification log.
- `plans/2026-08-23-registry-auth-retry.md` still owns the interactive-session auth-retry idea this
  plan deferred to it; its citation of this file's §3 is rewritten to point at `contributing/`.

# Release workflows

How a built artifact leaves this repo for an external registry, and why the GitHub Actions workflows
under `.github/workflows/` are shaped the way they are. The every-commit gate (`ci.yml`) runs
`inv quality.check` and nothing external; everything below is deliberate and occasional, never a
side effect of a push. Extracted from the now-retired
`plans/2026-08-22-docker-registry-integration.md`; the PyPI half is still open in
`plans/2026-08-22-pypi-publish-integration.md`.

## Docker images go to GHCR, authenticated by `GITHUB_TOKEN`

`ghcr.io` over Docker Hub, for a GitHub-hosted repo: CI auth is the job's already-issued
`GITHUB_TOKEN` with `permissions: packages: write`, through `docker/login-action`, so there is no
second account, no PAT to create, rotate, or store as a repo secret. Docker Hub would add all three
for no offsetting benefit. A human publishing from their own machine does a one-time
`docker login ghcr.io` with a PAT scoped to `write:packages`, kept in their own secret manager.
`docker.py` carries no auth handling in the CI path and none is planned — the token does not expire
mid-job and `docker/login-action` runs once up front. Its `docker.login` task exists for a human's
own machine and CI never calls it. Turning a stale-credential push failure into a pointer at that
task is still open in `plans/2026-08-23-registry-auth-retry.md`.

The image ref comes entirely from `repo-tasks.toml`'s `[[docker]]` entry; the workflow
(`docker-release.yml`) only logs in and runs `inv docker.release --project <name>`.

**GHCR rejects any uppercase character in an image ref.** This account's GitHub username is
`TheodoreAD`, so every ref derived from it — a `[[docker]]`/`[[helm]]` entry, CI's
`${{ github.repository_owner }}` — lowercases that segment explicitly (`ghcr.io/theodoread/...`).
Confirmed by the first push attempt, 2026-08-23.

**A new GHCR package is private by default, even when the publishing repo is public.** Nothing in
the workflow or the token controls this; making a package public is a one-time manual flip in its
settings on github.com, needed only once something outside the account has to pull it. Confirmed
2026-08-24: `ghcr.io/theodoread/sample-service` answered 401 to an anonymous tag listing right after
its first push from a public repo.

## Release candidates reach TestPyPI only

`publish.yml` triggers on both `vX.Y.Z` and `vX.Y.ZrcN` tags — the latter is what
`inv gitflow.release-candidate` pushes from the release branch
([`release-flow.md`](release-flow.md#the-release-candidate-cycle)). The TestPyPI job runs for
either; the real-index job is skipped for any tag containing `rc`, so a candidate is never one
approval click away from pypi.org, where a version number can never be reused. `docker.release`
gates itself the same way: an rc or dev build is pushed under its own tag and never as `latest`.

## Why `docker-release.yml` is dispatched by hand

A registry push is a real external side effect, so the workflow is `workflow_dispatch`-only
(`gh workflow run docker-release.yml -f project=sample-service`), and the every-commit tier pushes
to a throwaway local registry instead ([`test-tiers.md`](test-tiers.md)).

There is no tag-push trigger, and the obvious one would be wrong: `v*` tags name the root
`repo-tasks` project's version, while the sample image is versioned by the `sample-service` group.
Its own tag scheme, `<group>-vX.Y.Z` ([`versioning.md`](versioning.md)), is not emitted by
`version.py` yet — `tag_name` is hardcoded to `v{new_version}`. Add the trigger once that exists.

## Checking a workflow before dispatching it

Two local steps, both via tools in the `repo-tasks-quality` dependency group:

- `inv quality.workflow-check` — actionlint (correctness) and zizmor (security), both static; part
  of `inv quality.check`, so they run on every commit anyway. zizmor's `unpinned-uses` policy is
  relaxed to `ref-pin` in the shipped `zizmor.yml`; that file carries the reason.
- `inv test.workflows --event workflow_dispatch --job release --dry-run` — act prints the job's plan
  without running a container; drop `--dry-run` to run the job for real in a local container (Docker
  needed, and secrets such as `GITHUB_TOKEN` must be passed by hand). Not a tier and not in any
  gate.

The first real GHCR round trip was verified this way and then in CI:
[run 32762887843](https://github.com/TheodoreAD/repo-tasks/actions/runs/32762887843) pushed
`sample-service:0.1.0` and `:latest`.

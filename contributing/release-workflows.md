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
own machine and CI never calls it.

[DECISION: a push that fails on a stale credential is left with the tool's own error — no retry, no
re-auth cycle, and not even a printed pointer at `docker.login`/`helm.login`. Closed as abandoned
2026-09-05 (the now-retired `plans/2026-08-23-registry-auth-retry.md`), after its original design
was overtaken three times: CI turned out never to need it; the `login` tasks landed, dividing the
problem with the OS secret store (`plans/2026-08-30-registry-credentials-in-the-os-store.md`); and a
re-auth cycle would have this package drive an interactive login on the user's behalf, the opposite
of the stance both `login` tasks take. The residual print was rejected on its own terms: it would
key off string-matching another tool's human-readable, locale-sensitive output, helm's failure text
had never been measured, and `denied: unauthorized` is not actually a bad last word. Revisit only if
a real stale-credential failure turns out to confuse someone.]

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

## How a credential reaches CI: OIDC first, an env var second, a file never

Both sections above solve this the same way without saying so generally, and the general rule is
what a reader configuring a new target needs.

[DECISION: the ordering is **no secret at all, else a secret injected as an environment variable,
never a file.** No keyring, no `.netrc`, no local-dev hidden-file mechanism on a runner. The reasons
are mechanical rather than stylistic: `secretservice` needs a D-Bus session and an unlocked
collection, and a runner has neither — so a keyring lookup there cannot succeed, only fail or
silently return nothing. And a file-based secret on a runner is _written from_ a CI secret, making a
second copy of the same value on disk where a later step or a cached artifact can read it. It adds
exposure and buys nothing. Stated 2026-08-30.]

This is the exact inverse of the local rule, where every tool reaches the OS secret store through
its own native integration (`plans/2026-08-30-registry-credentials-in-the-os-store.md`). Local and
CI disagree on purpose.

| target                         | OIDC available              | fallback when it is not                                  |
| ------------------------------ | --------------------------- | -------------------------------------------------------- |
| PyPI (`uv publish`)            | **yes**, and already in use | `UV_PUBLISH_TOKEN`, or `UV_PUBLISH_USERNAME`/`_PASSWORD` |
| GHCR (`docker push`)           | **yes**, `GITHUB_TOKEN`     | `docker/login-action` with a repository secret           |
| an OCI chart registry (`helm`) | depends on the registry     | `helm registry login --password-stdin`, reading from env |

So no target in this family currently needs a secret at all: PyPI uses Trusted Publishing and GHCR
uses the job's own token. The rule is written down for the store that offers neither, and the
workflows deliberately carry no secret plumbing until such a target exists — commented-out
configuration for a speculative need is worse than a documented pattern.

[PITFALL: setting `keyring-provider` anywhere a consumer's CI can read it **disables Trusted
Publishing, silently.** In `uv-publish/src/lib.rs`'s `check_trusted_publishing`, with
`trusted-publishing = "automatic"` the guard
`username.is_some() || password.is_some() || keyring_provider != Disabled` returns
`TrustedPublishResult::Skipped` before any OIDC exchange is attempted; with `"always"` the same
condition becomes a hard `MixedCredentials` error. The local convenience and the CI path are in
direct tension, and the resolution is placement: `keyring-provider` belongs in the per-user
`~/.config/uv/uv.toml`, **never** in a committed `pyproject.toml` or `uv.toml`. Read from uv's
source 2026-08-30. The failure mode is the dangerous kind — "trusted publishing stopped working"
with no error naming the cause.]

Helm's fallback is the one that does not fully satisfy the rule:
`helm registry login
--password-stdin` keeps the secret off the command line and out of the process
table, but writes it into helm's registry config on the runner — a file. Whether that matters on an
ephemeral runner, or whether the login should be avoided entirely, is deliberately undecided; see
`plans/2026-08-30-ci-secrets-for-non-oidc-registries.md`. Do helm's case last if a non-OIDC target
ever arrives.

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

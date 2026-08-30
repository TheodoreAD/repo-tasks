---
status: idea
updated: 2026-08-30
---

# How a secret reaches CI for a store with no OIDC

## Context

The local half of the credential question is settled: every tool uses the OS secret store through
its own native integration
([`2026-08-30-registry-credentials-in-the-os-store.md`](2026-08-30-registry-credentials-in-the-os-store.md)).
None of that transfers to CI, and the user's framing 2026-08-30 was explicit:

> absolutely no keyring in the CI, that's an antipattern as far as I know along with netrc or any
> other local dev hidden-file secret based stuff.

That holds, and the reasons are mechanical rather than stylistic:

- `secretservice` needs a D-Bus session and an unlocked collection. A runner has neither, so a
  keyring lookup there cannot succeed — it can only fail, or silently return nothing.
- A file-based secret on a runner is written **from** a CI secret. It is a second copy of the same
  value, on disk, in a place a later step or a cached artifact can read. It adds exposure and buys
  nothing.

So the ordering is: **no secret at all, else a secret injected as an environment variable, never a
file.**

## The three consumers, and what each already supports

| target                         | OIDC available              | fallback when it is not                                  |
| ------------------------------ | --------------------------- | -------------------------------------------------------- |
| PyPI (`uv publish`)            | **yes**, and already in use | `UV_PUBLISH_TOKEN`, or `UV_PUBLISH_USERNAME`/`_PASSWORD` |
| GHCR (`docker push`)           | **yes**, `GITHUB_TOKEN`     | `docker/login-action` with a repository secret           |
| an OCI chart registry (`helm`) | depends on the registry     | `helm registry login --password-stdin`, reading from env |

PyPI is therefore **not** the case that needs a secret — Trusted Publishing is already the design in
[`2026-08-22-pypi-publish-integration.md`](2026-08-22-pypi-publish-integration.md) §3/§4, and it
exchanges a short-lived OIDC token for a short-lived upload token with nothing stored anywhere. The
question this plan exists for is the store that does **not** offer that.

[PITFALL: setting `keyring-provider` anywhere a consumer's CI can read it **disables Trusted
Publishing**, silently. From `uv-publish/src/lib.rs:421`: with `trusted-publishing = "automatic"`,
`username.is_some() || password.is_some() || keyring_provider != Disabled` returns
`TrustedPublishResult::Skipped`; with `"always"` it is a hard `MixedCredentials` error. So the local
convenience and the CI path are in direct tension, and the resolution is placement — the setting
belongs in the per-user `~/.config/uv/uv.toml`, never in a committed `pyproject.toml` or `uv.toml`.
Verified against uv's source, 2026-08-30.]

## Open questions

- [NEEDS CLARIFICATION: should the shipped workflows defend against that pitfall actively, by
  setting `UV_KEYRING_PROVIDER=disabled` in the publish job? It is already the default, so this only
  guards against a consumer that put the setting in a committed file — which is the mistake most
  worth catching, since its symptom is "trusted publishing stopped working" with no obvious cause.
  Against: config that exists solely to neutralise other config is its own smell, and it would ship
  to every consumer through `scaffoldapy`.]

- [NEEDS CLARIFICATION: does this belong in the shipped workflow templates at all, or only in
  `contributing/release-workflows.md` as a documented pattern? No target in this family currently
  needs a non-OIDC secret. Writing the pattern down costs nothing and rots slowly; wiring
  commented-out secret plumbing into `publish.yml` ships unused configuration to every generated
  repo, which is the shape `~/AGENTS.md` warns about for speculative needs.]

- [NEEDS CLARIFICATION: what is the naming convention for the secret, and who owns it? A repository
  secret, an environment secret tied to the existing `pypi` GitHub Environment (whose reviewer rule
  is already the real gate on the irreversible step), or an organisation secret. The environment
  variant composes with the protection rule already designed and is probably right, but it has not
  been priced.]

- [NEEDS CLARIFICATION: helm's CI path is the least worked out of the three.
  `helm registry login
  --password-stdin` reading from an env var keeps the secret off the command
  line and out of the process table, which is the same property `docker/login-action` gives for free
  — but it writes the credential into helm's registry config on the runner, i.e. a file, which is
  the thing this plan says not to do. Whether that matters on an ephemeral runner, or whether the
  write should be avoided entirely, needs deciding rather than assuming.]

## Recommended direction

Rough, and deliberately not built — nothing in the family needs it yet.

1. **Write the pattern down in `contributing/release-workflows.md`**, next to the existing
   GHCR/`GITHUB_TOKEN` reasoning: OIDC first, env-injected secret second, file never, with the
   `keyring-provider` pitfall stated where a reader configuring CI will meet it.
2. **Leave the workflows alone** until a real non-OIDC target exists. The one exception worth
   considering now is the `UV_KEYRING_PROVIDER=disabled` guard, which is a different decision from
   this plan's main question and is the first open question above.
3. **When a target does arrive**, do helm's case last — it is the one whose fallback still writes a
   file, and the only one where the answer might be "do not use the tool's login at all".

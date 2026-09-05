---
status: idea
updated: 2026-09-05
source_repo: github.com-personal/power-user-linux-setup
source_session: 25ea8788-b99d-43a2-9611-2d0c1f207694.jsonl
source_moment: 2026-09-05T18:40:00Z
---

# The machine has a credential helper now, so `docker.login`/`helm.login` can be verified

## Context

`plans/2026-08-30-registry-credentials-in-the-os-store.md` is
`blocked on power-user-linux-setup installing the credential helper`. **That happened on
2026-09-05.** This file exists so the block can be lifted with the machine's actual state to hand
rather than a claim that it was done.

## What landed on the machine

- **`docker-credential-secretservice` v0.9.9**, installed from upstream's release binary as a
  declared `[packages.docker-credential-secretservice]` entry, not a one-off. Upstream rather than
  noble's `golang-docker-credential-helpers` 0.6.4, decided with the user: three minor versions and
  years behind is too far for a component `oras` fails hard on. The `binary` install method was
  extended to resolve `{version}` into its URL for it, since upstream names the version in the asset
  filename.
- **`"credsStore": "secretservice"` written explicitly** into `~/.docker/config.json`, preserving
  every other key. Explicit rather than detected for the reason that plan's own pitfall gives: the
  machine already had an `auths` entry, so `ContainsAuth()` was true and detection would never have
  run.
- **A round-trip check, run before anything is written and hard-failing if it does not pass.** Store
  a throwaway credential through the helper, read it back, compare, erase. Verified live against the
  running Secret Service, and additionally corroborated by `gh auth status` reporting `(keyring)`.
- **`inv docker.configure-credential-store`** in that repo's setup packages phase, after
  `tools.install`. On a machine with no helper — the package is `workstation`-tagged — it prints
  that credentials stay in the file and returns, rather than degrading silently.

## What this unblocks, and the one thing it does not

The `[UNVERIFIED:]` in that plan can now be run:

```shell
inv docker.login          # against ghcr.io
docker-credential-secretservice list   # or `get`, to confirm the credential is in the keyring
```

then confirm **no new `auths` entry appeared** in `~/.docker/config.json`. That second half is the
whole test — `credsStore` being set does not stop docker reading a pre-existing plaintext entry, so
"the login worked" is not evidence about where the credential went.

Then `inv helm.login` **against a host that is not an image registry**, exactly as that plan
specifies. The same-host case cannot distinguish helm storing its own credential from helm reading
docker's through the fallback, and this machine's `repo-tasks.toml` happens to put images and charts
on the same `ghcr.io`, so the distinguishing run needs a host chosen deliberately.

**The machine now holds no plaintext registry credential at all**, which removes the one hazard this
section originally warned about. It had one — an obsolete work registry — and the user's call was
that nothing local needs it: the only images published from that machine go to GHCR, from a CI
workflow rather than locally. Removed the same day through
`inv docker.configure-credential-store --purge-plaintext`, an opt-in flag on the same task, which
strips the secret fields and then deletes any entry left holding nothing — the same two effects
`docker logout` has on that file. **`auths` is now `{}`**, so no registry hostname remains there
either.

[PITFALL: an earlier form of that flag kept the emptied entry, justified as "the state
`docker logout` leaves". Read from `docker/cli` afterwards, that is backwards in both halves:
`nativeStore.Erase` delegates to `fileStore.Erase`, which **deletes** the entry, while a secretless
entry is what `nativeStore.Store` writes on **login** to keep the email. Worth knowing here because
the verification below reads that file to decide whether a credential went to the keyring: an entry
present with no secret means a login through the helper, not a leftover.]

So any host is now a sound choice for the verification: nothing can resolve from a file entry and be
mistaken for the keyring path. The only distinction still worth respecting is this plan's original
one — run `helm.login` against a host that is **not** an image registry, so the docker fallback
cannot mask a helm-side failure.

## Recommended direction

1. Lift the `blocked on ...` status on
   [`2026-08-30-registry-credentials-in-the-os-store.md`](2026-08-30-registry-credentials-in-the-os-store.md)
   and run its verification, both tools, helm against a distinct host.
2. Record which way it went. That plan's whole remaining content is an `[UNVERIFIED:]` about whether
   the login tasks produce a keyring entry or a file entry, and nothing else in the family answers
   it.
3. Only then consider its `[DEFERRED:]` nicety — `helm.login` noticing that its chart host matches a
   `[[docker]]` entry's host. It is guidance about a machine state that repo cannot see, and the
   verification is what tells you whether the guidance would be true.

[NEEDS CLARIFICATION: what a CI runner does about all of this stays out of scope here and belongs to
[`2026-08-30-ci-secrets-for-non-oidc-registries.md`](2026-08-30-ci-secrets-for-non-oidc-registries.md)
— no keyring, no credential file, no netrc on a runner. Noted only because "the machine has a helper
now" invites exactly that question in the same breath.]

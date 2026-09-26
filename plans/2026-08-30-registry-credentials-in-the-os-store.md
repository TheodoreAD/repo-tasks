---
status: planned
updated: 2026-09-26
---

# Both `docker.login` and `helm.login` reach the OS secret store, once the machine has a helper

## Context

The household rule, 2026-08-30: **anything needing a password uses the OS secret store through
whatever native integration the tool already has.** `keyring` is a machine-provided CLI, never a
dependency of this package, and only a fallback for a tool with no native path.

`docker.login` and `helm.login` landed the same day (`ccc9dcd`). Neither reads, stores or echoes a
credential — each resolves the registry host from `repo-tasks.toml` and hands off to the tool's own
interactive login. Whether that is _secure_ is entirely a property of the machine, which is why this
plan sat `blocked on` that machine having a credential helper. **It has one as of 2026-09-05** —
what landed is below — so what remains is running the verification, not waiting for anything.

**This plan replaces `2026-08-30-helm-credentials-outside-the-os-store.md`, whose central claim was
wrong.** That version said helm cannot reach the OS secret store and had it as the plan's whole
question. Reading helm and oras source settled it the other way; the correction is below, kept
because the reasoning that produced the wrong answer is the reasoning a future session would repeat.

## What was measured, from source

Clones in `$RESEARCH_HOME/repos/`: `github.com--helm--helm`, `github.com--docker--cli`,
`github.com--oras-project--oras-go` (with the `v2.6.2` tag helm 4.2.4 actually pins),
`github.com--astral-sh--uv`.

### The gate that governs everything

Docker and oras both auto-detect a credential helper, and both gate detection on the config file
having **no authentication in it yet**:

```go
// docker/cli, cli/config/config.go:173
if !configFile.ContainsAuth() {
    configFile.CredentialsStore = credentials.DetectDefaultStore(configFile.CredentialsStore)
}
```

`ContainsAuth()` is `credsStore != "" || len(credHelpers) > 0 || len(auths) > 0`
(`cli/config/configfile/file.go:148`). oras' `IsAuthConfigured()` counts the same three things.

[PITFALL: **an existing plaintext `auths` entry suppresses the secure default.** It is not merely
that the entry stays insecure — its presence stops detection from ever running, so installing the
helper changes nothing on a machine that has ever logged in before. This machine is in exactly that
state, which is why `credsStore` is set explicitly rather than left to detection: an explicit value
is read at step 2 of the resolution order below and never depends on what else is in the file.]

### How a credential is keyed, and why one login can serve both tools

The store is a key/credential map keyed by **registry host**:

```go
// oras v2.6.2 registry/remote/credentials/registry.go:87
func ServerAddressFromRegistry(registry string) string {
    if registry == "docker.io" || registry == "registry-1.docker.io" {
        return "https://index.docker.io/v1/"  // Docker Hub's legacy key
    }
    return registry                            // everything else: the plain host
}
```

helm builds `NewStoreWithFallbacks(helmOwnStore, dockerStore)` (`pkg/registry/client.go:118`), where
`Get()` searches primary **and** fallbacks while `Put()` writes to the primary only. So
`docker login ghcr.io` writes key `ghcr.io`, and `helm push oci://ghcr.io/...` finds it through the
docker fallback.

[PITFALL: that only holds **when the hosts coincide**, and this repo's `repo-tasks.toml` happens to
put images and charts on the same `ghcr.io`. A chart registry on a different host than any image
registry gets nothing from `docker login`, because the lookup is per-host. `helm.login` is therefore
not redundant, and an earlier draft of this plan wrongly proposed dropping it on the strength of
this repo's own configuration.]

Resolution order inside the store, `getHelperSuffix`: per-registry `credHelpers[host]` → global
`credsStore` → the detected default. The detected default on Linux is `pass` when that binary is on
`PATH`, else `secretservice`.

[PITFALL: docker checks the helper binary exists before returning it
(`exec.LookPath("docker-credential-" + name)`, `credentials/default_store.go`) and degrades to
plaintext when it does not. **oras does not.** `getPlatformDefaultHelperSuffix` returns
`"secretservice"` unconditionally, and `getStore` then returns `NewNativeStore(helper)` with no
existence check and no fallback. So on a machine with no helper installed and a fresh helm config,
`helm registry login` selects a store that fails when it execs, rather than falling back. Installing
the helper is what protects this, and it is a reason the machine setup must not be half-done.]

## The machine has the helper now (2026-09-05)

`power-user-linux-setup` landed its half the same week, which is what lifts this plan's `blocked on`
status. What is actually on the machine, recorded here rather than taken on trust that the filed
plan was followed:

- **`docker-credential-secretservice` v0.9.9**, from upstream's release binary as a declared
  package, not a one-off. Upstream rather than noble's `golang-docker-credential-helpers` 0.6.4 —
  three minor versions and years behind is too far for a component `oras` fails hard on. That repo's
  `binary` install method was extended to resolve `{version}` into the URL, since upstream names the
  version in the asset filename.
- **`"credsStore": "secretservice"` written explicitly** into `~/.docker/config.json`, preserving
  every other key. Explicit rather than detected, for exactly the reason this plan's first pitfall
  gives: the machine already had an `auths` entry, so `ContainsAuth()` was true and detection would
  never have run.
- **A round-trip check that runs before anything is written and hard-fails if it does not pass** —
  store a throwaway credential through the helper, read it back, compare, erase. Verified live
  against the running Secret Service, and corroborated by `gh auth status` reporting `(keyring)`.
- **`inv docker.configure-credential-store`** in that repo's setup packages phase, after
  `tools.install`. On a machine with no helper it prints that credentials stay in the file and
  returns, rather than degrading silently.

**The machine now holds no plaintext registry credential at all.** It had one — an obsolete work
registry — and the user's call was that nothing local needs it, since the only images published from
this machine go to GHCR from a CI workflow. Removed the same day with `--purge-plaintext`, an opt-in
flag that strips the secret fields and then deletes any entry left holding nothing. **`auths` is now
`{}`**, so no registry hostname remains there either.

[PITFALL: an earlier form of that flag kept the emptied entry, justified as "the state
`docker logout` leaves". Read from `docker/cli` afterwards, that is backwards in both halves:
`nativeStore.Erase` delegates to `fileStore.Erase`, which **deletes** the entry, while a secretless
entry is what `nativeStore.Store` writes on **login**, to keep the email. That matters directly to
the verification below, which reads that file to decide where a credential went: **an entry present
with no secret means a login through the helper, not a leftover.**]

## What is left here

Nothing left, as of 2026-09-26: both login paths put the credential in the OS keyring, and the
same-host hint is built. The plan is ready to retire.

**The docker half, verified 2026-09-26.** `docker login ghcr.io` against the machine's explicit
`credsStore: secretservice`, then both places a credential could land were read:

- `docker-credential-secretservice list` returned
  `{"Registry credentials for ghcr.io":"TheodoreAD"}`, so the credential is in the OS keyring.
- `~/.docker/config.json` went from `auths: {}` to `auths: {"ghcr.io": {}}`, an entry with **no**
  fields: the secretless shape `nativeStore.Store` writes on a helper login, per the pitfall above.
  Nothing base64 was written to the file.

[PITFALL: **this ran `docker login` with `--password-stdin`, not `inv docker.login`**, because the
Bash tool an agent drives has no TTY and `run_interactive` needs one to prompt. That is the same
code path for the question asked here — where docker puts the credential is decided by `credsStore`
and not by how the password arrived — and the task's own contribution, the host taken from
`repo-tasks.toml`, is unit-tested. The password was the `gh` CLI's OAuth token, which GHCR accepted
for login even though that token carries no `read:packages` scope, so it proves the storage path and
not that the stored credential can push or pull. A push-capable login is a PAT or CI's
`GITHUB_TOKEN`.]

~~[UNVERIFIED: that `helm.login` results in a credential in the OS keyring.~~ **Verified 2026-09-26,
against a local registry rather than a hosted one.** The check needed a host that is not also an
image registry, since helm reads docker's store as a fallback and `ghcr.io` now holds a docker
credential. A local `registry:2` on `localhost:5000` with htpasswd auth and a throwaway user is such
a host, needs no account, and sends nothing off the machine. Helm's own registry config did not
exist beforehand, so this also exercised oras's detection path, the one the pitfall above says fails
hard when the helper is missing.

- `helm registry login localhost:5000 --password-stdin --plain-http` succeeded.
- `docker-credential-secretservice list` then held `localhost:5000` beside `ghcr.io`.
- `~/.config/helm/registry/config.json` was **created** holding `credsStore: secretservice` and
  `auths: {}`: detection chose the helper, wrote the choice down, and left no entry for the host at
  all, not even a secretless one. `~/.docker/config.json` was untouched, as `Put()` writes the
  primary store only.
- `helm push` of a throwaway chart to `oci://localhost:5000/charts` succeeded, so the credential
  reads back out of the keyring and not only goes in.
- **The control:** after `helm registry logout localhost:5000` the keyring entry was gone and the
  same push failed with `basic credential not found`. The registry refuses anonymous pushes, so the
  first push succeeding is evidence it used the stored credential.

Same caveat as the docker half: stdin rather than `inv helm.login`'s prompt, for the same TTY
reason, with the task's own contribution (the host) unit-tested. The container was removed
afterwards. One change outlives the check, deliberately: helm's registry config now exists with an
explicit `credsStore`, which is the state the machine setup would want anyway, and it is no longer
subject to detection.]

[PITFALL: **a local registry is the sound target for this check, not just the convenient one.** A
hosted second registry would have needed an account, and anything on `ghcr.io` would have passed
through the docker fallback whatever helm's own store did. The same shape answers any future "where
did this credential go" question for an OCI tool: a host nothing else has a credential for, a push
that must authenticate, and a logout-then-push control.]

~~[DEFERRED: whether `helm.login` should notice that its chart registry host matches a `[[docker]]`
entry's host.~~ **Built 2026-09-26, the user's call, after measuring the shared path first.**
`helm.login` says when an image registry shares the host, and still logs in; `helm.logout` says the
same and names `inv docker.logout` as the next step. The host match reuses `docker.py`'s own
`registry_host`, made public for it, so a bare `org/web` image counts as Docker Hub exactly as
docker would read it.

The measurement, against a local htpasswd `registry:2` with only a **docker** login:

- `helm push` with helm's own config succeeded, and so did `helm push --registry-config` pointing at
  a file-store config whose only `auths` entry was an unrelated host. The second is the fallback,
  proved rather than read from `NewStoreWithFallbacks`: helm's primary store had nothing for the
  host.
- `helm registry logout localhost:5000` then **erased docker's credential from the keyring**, and
  the fallback push failed with `basic credential not found`. `~/.docker/config.json` was left
  holding a secretless `localhost:5000` entry that pointed at nothing, which `docker logout`
  cleared.

[PITFALL: **the logout docstrings pushed earlier the same day were wrong, and only this measurement
caught it.** They said each tool's logout clears its own store and not the other's. With both
configs naming `credsStore: secretservice`, which is this machine's state since helm's first login
wrote it, the keyring holds **one** entry per host and both tools read and erase it. Each tool's
logout therefore ends both tools' access, and helm's also strands a dangling entry in docker's file.
Corrected in both docstrings. The hint is worded for either machine state: which one applies depends
on config the task does not read, and `inv docker.logout` is the right next step in both.]

## Recommended direction

1. ~~Wait for the machine setup~~ — landed 2026-09-05, recorded above. It was filed for
   `power-user-linux-setup` as `2026-08-30-os-secret-store-for-registries-and-pypi.md` and owned the
   helper package, the explicit `credsStore`, the round-trip verification, and migrating the one
   plaintext credential that existed.
2. ~~Run the verification above~~ — both halves done 2026-09-26, recorded above.
3. ~~Only then consider the deferred nicety~~ — built 2026-09-26, recorded above.

The CI half is deliberately not here: no keyring and no credential file belongs on a runner, and how
a secret reaches CI for a store without OIDC is its own design —
[`2026-08-30-ci-secrets-for-non-oidc-registries.md`](2026-08-30-ci-secrets-for-non-oidc-registries.md).
"The machine has a helper now" invites that question in the same breath and it is still out of scope
here.

The machine-side half of this section is merged in from
`2026-09-05-credential-helper-installed-logins-verifiable.md`, filed for this repo from that
consumer's own session (`25ea8788-b99d-43a2-9611-2d0c1f207694.jsonl`, around 2026-09-05T18:40Z) and
absorbed 2026-09-06 — the name to search for with `plans.py archive` if the original filing is ever
wanted.

---
status: planned
updated: 2026-09-06
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

Nothing to build. The tasks exist and are correct; what is missing is any evidence they do what
their docstrings say — and as of 2026-09-05 that evidence can be produced.

[UNVERIFIED: that either login task actually results in a credential in the OS keyring rather than a
base64 entry in a file. Both are unit-tested for command construction only. The check:

```shell
inv docker.login                       # against ghcr.io
docker-credential-secretservice list   # or `get`, to confirm the credential is in the keyring
```

then read `~/.docker/config.json` with the pitfall above in hand — a **secretless** entry is
evidence of a login through the helper, and only a secret-bearing one is the failure. With `auths`
now `{}`, any host is a sound choice for the docker half: nothing can resolve from a file entry and
be mistaken for the keyring path.

Then `inv helm.login` against a host that is **not** an image registry. That distinction still
stands, and is the one thing the purge does not remove: the same-host case cannot distinguish helm
storing its own credential from helm reading docker's through the fallback, and this repo's
`repo-tasks.toml` happens to put images and charts on the same `ghcr.io`. Both halves want a
deliberate session — they are interactive logins against a real account, not something to fold into
unrelated work.]

[DEFERRED: whether `helm.login` should notice that its chart registry host matches a `[[docker]]`
entry's host and say that one login covers both. Useful, and pure output — but it is guidance about
a machine state this repo cannot see, and it should not be written before the verification above
proves what the shared path actually does.]

## Recommended direction

1. ~~Wait for the machine setup~~ — landed 2026-09-05, recorded above. It was filed for
   `power-user-linux-setup` as `2026-08-30-os-secret-store-for-registries-and-pypi.md` and owned the
   helper package, the explicit `credsStore`, the round-trip verification, and migrating the one
   plaintext credential that existed.
2. **Run the verification above**, both tools, with the helm check on a distinct host. This is now
   the whole of what this plan is waiting on, and it is the only thing in the family that can answer
   its `[UNVERIFIED:]`.
3. **Only then consider the deferred nicety.** It is guidance about a machine state this repo cannot
   see, and the verification is what says whether the guidance would be true.

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

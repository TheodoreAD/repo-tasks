---
status: blocked on power-user-linux-setup installing the credential helper, which is what the login tasks need in order to store anything securely
updated: 2026-08-30
depends_on: [power-user-linux-setup]
---

# Both `docker.login` and `helm.login` reach the OS secret store, once the machine has a helper

## Context

The household rule, 2026-08-30: **anything needing a password uses the OS secret store through
whatever native integration the tool already has.** `keyring` is a machine-provided CLI, never a
dependency of this package, and only a fallback for a tool with no native path.

`docker.login` and `helm.login` landed the same day (`ccc9dcd`). Neither reads, stores or echoes a
credential — each resolves the registry host from `repo-tasks.toml` and hands off to the tool's own
interactive login. Whether that is _secure_ is entirely a property of the machine, which is why this
plan is blocked rather than open.

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

## What is left here

Nothing to build. The tasks exist and are correct; what is missing is any evidence they do what
their docstrings say, and that evidence cannot be produced until the machine has a helper.

[UNVERIFIED: that either login task actually results in a credential in the OS keyring rather than a
base64 entry in a file. Both are unit-tested for command construction only. The check, once
`power-user-linux-setup` has installed the helper and set `credsStore`: run `inv docker.login`
against `ghcr.io`, then confirm the credential is retrievable through
`docker-credential-secretservice get` and that no new `auths` entry appeared in
`~/.docker/config.json`. Then `inv helm.login` against a host that is **not** an image registry, so
the docker fallback cannot mask a helm-side failure — the same-host case cannot distinguish helm
storing its own credential from helm reading docker's.]

[DEFERRED: whether `helm.login` should notice that its chart registry host matches a `[[docker]]`
entry's host and say that one login covers both. Useful, and pure output — but it is guidance about
a machine state this repo cannot see, and it should not be written before the verification above
proves what the shared path actually does.]

## Recommended direction

1. **Wait for the machine setup.** It is filed for `power-user-linux-setup` as
   `2026-08-30-os-secret-store-for-registries-and-pypi.md` and owns the helper package, the explicit
   `credsStore`, the round-trip verification, and migrating the one plaintext credential that exists
   today.
2. **Then run the verification above**, both tools, with the helm check on a distinct host.
3. **Only then consider the deferred nicety.**

The CI half is deliberately not here: no keyring and no credential file belongs on a runner, and how
a secret reaches CI for a store without OIDC is its own design —
[`2026-08-30-ci-secrets-for-non-oidc-registries.md`](2026-08-30-ci-secrets-for-non-oidc-registries.md).

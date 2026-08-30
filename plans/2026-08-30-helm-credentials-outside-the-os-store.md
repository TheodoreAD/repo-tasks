---
status: idea
updated: 2026-08-30
---

# `helm registry login` cannot reach the OS secret store, and `docker login` can

## Context

The household rule, stated 2026-08-30: **anything needing a password uses the OS secret store, via
whatever native integration the tool already has.** `keyring` is a machine-provided CLI
(`[packages.python-keyring]` in `power-user-linux-setup`'s `setup.toml`, on `PATH` as
`~/.local/bin/keyring`) and is never a dependency of this package or anything it ships — it is only
ever a fallback for a tool with no native path of its own.

Docker has that native path. `~/.docker/config.json`'s `credsStore` names a helper — the value is
the suffix of a `docker-credential-*` binary — and docker consults it for every command, so nothing
in `repo-tasks` ever handles a credential. `inv docker.login` therefore automates only the registry
host, which comes from `repo-tasks.toml`.

Helm does not, and that asymmetry is what this plan is about.

## What was measured

Against the installed versions on 2026-08-30 — helm **v4.2.4**, docker **29.7.2**, uv **0.11.19** —
rather than against the issue tracker:

- `helm registry login --help` offers `-u`, `-p`, `--password-stdin`, `--registry-config` and TLS
  flags. **There is no credential-helper option of any kind**, and `--registry-config` defaults to
  `~/.config/helm/registry/config.json`, not to docker's config.
- So a `helm registry login` today writes a base64 `auth` entry into helm's own file. Base64 is
  encoding, not encryption — the credential is readable by anything that can read the file.

Upstream reports the same shape: helm does not pick up `credHelpers` from `DOCKER_CONFIG`
([helm#13228](https://github.com/helm/helm/issues/13228)), cannot reuse an existing docker config
for auth ([helm#10156](https://github.com/helm/helm/issues/10156)), and "where does helm store
registry credentials" is a recurring question
([helm#13571](https://github.com/helm/helm/issues/13571)).

[PITFALL: `credHelpers` and `credsStore` are different keys and the upstream reports are about the
first. `credHelpers` maps one registry to one helper; `credsStore` names a single global helper.
That helm ignores the per-registry map is not evidence that it ignores the global one, and the
distinction is exactly the kind that gets flattened into "helm doesn't support credential helpers"
and then believed. It has not been tested here, because testing it needs a `credsStore` configured
first — see the dependency below.]

## Open questions

- [NEEDS CLARIFICATION: does `helm registry login --registry-config ~/.docker/config.json` honour a
  `credsStore` set in that file? If it does, the whole problem is one flag on two tasks, and helm
  and docker share one credential in one secure place. If it does not, helm's credential cannot
  reach the OS secret store at all through helm's own CLI. This is the question the plan turns on
  and it is a single measurement, blocked only on the machine having a helper installed.]

- [NEEDS CLARIFICATION: if the answer is no, what is the fallback? Options, none costed yet: accept
  helm's base64 file and document it; write helm's config from `keyring` at login time via
  `--password-stdin` (the credential crosses a pipe, never a command string, so nothing is echoed —
  but the result still lands base64 in helm's file, so this secures the _source_ and not the
  _store_); or push charts with something other than helm's own CLI, which is a much larger change.]

- [NEEDS CLARIFICATION: does `oras` — which helm uses underneath for OCI — honour docker's
  credential helpers when helm's own CLI does not? If so, a chart push could go through a path that
  does reach the secret store. Unresearched.]

[UNVERIFIED: `docker.login`'s own claim. The task runs `docker login <host>` and relies on docker's
helper to store the result, but this machine has **no `credsStore` configured and no
`docker-credential-*` helper installed**, so today it stores a base64 `auth` entry exactly like
helm. The docker half of the household rule is only true once the machine setup lands — filed for
`power-user-linux-setup` as `2026-08-30-os-secret-store-for-registries-and-pypi.md`, since the
package and the config both belong there. Until then `docker.login` is correct in shape and insecure
in effect, and this note is the only thing saying so.]

## Recommended direction

Rough, and the order matters because the first item unblocks the measurement everything else needs.

1. **The machine setup lands first**, in `power-user-linux-setup`: the helper package and
   `credsStore`. Nothing here can be tested before it.
2. **Then run the one measurement** — `helm registry login --registry-config ~/.docker/config.json`
   against a real registry, and check whether the credential lands in the secret store or in the
   file. One command, and it decides the plan.
3. **Only then choose a fallback**, if one is needed. Do not build the `keyring`-piping variant
   before the measurement: it is the more complex option and it may turn out to be unnecessary.

The `[UNVERIFIED:]` tag in `helm.login`'s own docstring points here, so a reader of the task finds
this rather than assuming the task does more than it does.

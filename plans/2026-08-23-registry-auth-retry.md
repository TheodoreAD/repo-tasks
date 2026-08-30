---
status: idea
updated: 2026-08-30
---

# Turn a push's auth failure into the login task that already fixes it

## Context

Extracted from the now-retired `plans/2026-08-19-docker-image-tasks.md`'s
`### 4. Auth — deferred, not dropped` during the now-retired plan-retirement pass. It was explicitly
written down there "so it isn't silently forgotten" — inside a file marked `landed` whose retirement
ends in `rm`, which is precisely how it would have been.

The now-retired `plans/2026-08-19-helm-chart-tasks.md` §4 deferred the same idea for `helm push` to
this plan and named the same shared `src/repo_tasks/_registry_auth.py` helper, so this plan owns the
behavior for both rather than either one implementing it privately.

**The plan as filed has been overtaken three times, and what survives is the option it never
seriously considered.** Reviewed 2026-08-30; each shift is recorded below because the original
design is still the first thing a future session would find, and it is no longer the right one.

### 1. CI never needed it — established 2026-08-24

[`contributing/release-workflows.md`](../contributing/release-workflows.md) (from the now-retired
`plans/2026-08-22-docker-registry-integration.md`) established that the CI path needs none of this:
`docker/login-action` + `GITHUB_TOKEN` authenticates once up front and `GITHUB_TOKEN` doesn't expire
mid-job — verified by a real `inv docker.release` run against GHCR. The retry logic was already down
to one audience: a human on one machine whose local credential went stale.

### 2. The login tasks landed — 2026-08-30

`docker.login` (`docker.py:144`) and `helm.login` (`helm.py:110`) both exist as of `ccc9dcd`, each
resolving the registry host from `repo-tasks.toml` and handing off to the tool's own interactive
login. When this plan was written, `docker.py` had `build`/`push`/`release`/`_resolve_image` and
nothing else, and half the stated motivation for a shared `_registry_auth.py` was that `helm.py` did
not exist at all.

That is the shift that matters most, and it cuts both ways. It removes the reason to design a shared
auth module — the shared surface got built, as two per-tool tasks. It also **hands the cheap option
its missing piece**: detect-and-instruct had nothing specific to instruct with in 2026-08-23, and
now it has an exact task name to print.

### 3. The keyring question is answered — 2026-08-30

The household rule recorded in
[`2026-08-30-registry-credentials-in-the-os-store.md`](2026-08-30-registry-credentials-in-the-os-store.md):
**anything needing a password uses the OS secret store through whatever native integration the tool
already has**, and `keyring` is a machine-provided CLI, never a dependency of this package. The
original question — whether a cross-platform keyring binding was justified as this package's first
non-quality runtime dependency — is settled as a no, family-wide, and not by this plan.

## What is actually left

One small thing, in the shape the package has since standardised on. `_next_steps()` was
`gitflow.py`'s local convention when this plan proposed reusing it; it is now imported by `venv.py`,
`configs.py` and `deps.py` as well, so printing a next command is how every module in this package
tells a human what to run.

So the residue is: `docker.push`/`helm.push` notice an auth failure and print `inv docker.login` /
`inv helm.login`, instead of leaving the tool's raw `denied: unauthorized` as the last word. No new
module, no new dependency, no shared abstraction, no re-auth cycle.

**The full re-auth cycle is rejected, not deferred.** It was designed for a CI path that turned out
not to need it, its credential-storage half is now answered by the OS secret store, and it would
have this package drive an interactive login on a user's behalf — which is the opposite of the
stance `quality.py` and both `login` tasks take.

## Open questions

[NEEDS CLARIFICATION: is even the print worth it? Against: the tools' own errors are not actually
bad, every other tool in the ecosystem behaves this way, and a wrong guess prints misleading advice.
For: this package's whole stance is that a human should be told the next `inv` command rather than
left to know it, and there is now a task name that is genuinely the right answer.]

[NEEDS CLARIFICATION: what signal to key off. The original design matched `docker push` output for
`401`/`unauthorized` — string-matching another tool's human-readable output, which drifts across
versions and is locale-sensitive. Worth checking whether docker and helm distinguish an auth failure
by exit code at all before writing a matcher; if string matching is the only lever, that is an
argument for keeping the consequence cheap, which the print already is. Note this machine's mixed
locale (`LC_MESSAGES` stays `en_US.UTF-8`, so the message text is stable here) is not a property a
consumer's machine shares.]

[NEEDS CLARIFICATION: helm's failure output has still never been looked at. The original plan
assumed "identical behavior" for docker and helm without checking, and that assumption was
unverifiable then because `helm.py` did not exist. It exists now, so this is a five-minute
measurement rather than an open design question — and it decides whether one matcher serves both or
each push grows its own two-line check.]

## Recommended direction

Do not build the shared helper. Nothing in the original design survives its three overtakings
intact, and rebuilding it would add a module and a dependency to solve a problem that the `login`
tasks and the OS secret store have already divided between them.

If anything is built, it is two or three lines inside each `push`, reusing `_next_steps()`. Measure
helm's and docker's actual auth-failure output first — the third question above — because a matcher
written against one tool's message and assumed to fit the other is exactly the mistake the original
plan already made once.

Otherwise close this as `abandoned` and let the tools' own errors stand. That is a legitimate
outcome and the plan should not be kept alive out of momentum: what it was filed to protect has been
built, and what it originally designed has been rejected on the evidence.

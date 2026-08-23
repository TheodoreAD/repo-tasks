---
status: idea
updated: 2026-08-23
---

## Context

Extracted from the now-retired `plans/2026-08-19-docker-image-tasks.md`'s
`### 4. Auth — deferred, not dropped` during `plans/2026-08-23-plan-retirement-and-tagging.md`. It
was explicitly written down there "so it isn't silently forgotten" — inside a file marked `landed`
whose retirement ends in `rm`, which is precisely how it would have been.

The now-retired `plans/2026-08-19-helm-chart-tasks.md` §4 deferred the same idea for `helm push` to
this plan and named the same shared `src/repo_tasks/_registry_auth.py` helper, so this plan owns the
behavior for both rather than either one implementing it privately.

Current state, confirmed 2026-08-23: `src/repo_tasks/docker.py` has no auth handling of any kind
(`build`/`push`/`release`/`_resolve_image` only), and `_registry_auth.py` does not exist.
`docker
login` being already done is the caller's responsibility, matching `quality.py`'s
no-secrets-touched stance.

**The premise has weakened since it was written, and that is the first thing to settle.**
`plans/2026-08-22-docker-registry-integration.md` §3 established that the CI path needs none of
this: `docker/login-action` + `GITHUB_TOKEN` authenticates once up front and `GITHUB_TOKEN` doesn't
expire mid-job. That plan says so directly — the retry logic "remains meaningful only for a human's
local/interactive session hitting a stale credential." So the remaining audience is one developer on
one machine whose SSO session lapsed, which may not justify a shared helper module at all.

## Open questions

[NEEDS CLARIFICATION: is this worth building? With CI covered by `docker/login-action`, the only
beneficiary is a human whose local credential went stale — for whom the current behavior (a clear
`denied`/`unauthorized` from the docker CLI, then `docker login`) is arguably fine, and is what
every other tool does. The honest options are: build it as designed, reduce it to a
_detect-and-instruct_ step (catch the 401, print the exact `docker login`/`helm registry login`
command to run — matching `gitflow.py`'s established `_next_steps()` convention), or close this as
`abandoned`. The middle option looks strongest and was never considered when the original §4 was
written, because `_next_steps()` didn't exist yet.]

[NEEDS CLARIFICATION: the original design keys off "`docker push` output containing
`401`/`unauthorized`". That is string-matching another tool's human-readable output, which drifts
across docker versions and is locale-sensitive. Is there a structured signal instead — an exit code
that distinguishes auth failure from any other push failure, or
`docker system info`/`docker
manifest inspect` as a pre-flight check? If string matching is the only
option, that is itself an argument for the detect-and-instruct option above, since a false positive
that merely prints wrong advice is much cheaper than one that triggers a spurious re-auth cycle.]

[NEEDS CLARIFICATION: `keyring` would be the first runtime dependency this package adds for a
non-quality concern (current dev-time set is `ruff`/`basedpyright`/`dprint`/`shfmt`/
`bump-my-version`, and the runtime set is essentially just `invoke`). Is a cross-platform keyring
binding justified when docker's own credential helpers already solve credential storage, and when
`repo-tasks` explicitly "never stores, generates, or invents credentials itself"?]

[NEEDS CLARIFICATION: if a shared helper is built, is `_registry_auth.py` the right shape given this
repo's "one module per facility, named after what it owns" convention (`AGENTS.md`)? A leading
underscore marks it private-to-the-package, but it would be the first such module — every existing
one is a public task module. An alternative is a small non-task module with no underscore, since the
convention is about what a module _owns_, not about whether it exports tasks.]

[NEEDS CLARIFICATION: `helm push` and `docker push` fail differently and authenticate differently
(`helm registry login` vs `docker login`, different output). How much is genuinely shared versus two
thin per-tool implementations behind one interface? The original design assumed "identical behavior"
without checking helm's actual failure output — unverifiable until `helm.py` exists at all.]

## Recommended direction

Rough, not designed. Settle the first open question before any of the others: if the answer is
detect-and-instruct, most of this plan evaporates into a few lines inside `docker.py`'s existing
`push`, reusing `gitflow.py`'s `_next_steps()` pattern, with no new module, no new dependency, and
no shared abstraction to design.

Do not build the full re-auth cycle just because it was written down first — the CI wiring that
landed since removed its main justification, and the original design deferred it on the grounds that
"the release flow doesn't quietly become more manual than it needs to be" — a concern that
`docker/login-action` has now answered for the automated path.

Sequencing: this was waiting on `helm.py` existing at all, since half the stated motivation is
sharing with a module that didn't exist. It landed 2026-08-23, so nothing blocks this plan now.

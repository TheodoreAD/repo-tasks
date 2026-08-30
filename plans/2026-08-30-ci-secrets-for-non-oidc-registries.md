---
status: idea
updated: 2026-08-30
---

# How a secret reaches CI for a store with no OIDC

## Context

The pattern this plan existed to write down is **written down**. Landed 2026-08-30 in
[`../contributing/release-workflows.md`](../contributing/release-workflows.md), "How a credential
reaches CI": the OIDC-first / env-var-second / file-never ordering with the mechanical reasons, the
three-target table, and the `keyring-provider` pitfall placed where a reader configuring CI will
meet it.

That also answers the plan's second open question — the pattern belongs in `contributing/`, and the
shipped workflow templates stay untouched. No target in this family needs a non-OIDC secret today,
and commented-out secret plumbing shipped to every generated repo is the speculative-need shape
`~/AGENTS.md` warns about.

The `keyring-provider` finding was re-read from uv's source while writing that section rather than
carried over on trust: `check_trusted_publishing` in `crates/uv-publish/src/lib.rs` returns
`TrustedPublishResult::Skipped` under `"automatic"` and raises `MixedCredentials` under `"always"`,
both before any OIDC exchange. Unchanged from the 2026-08-30 reading.

## Open questions

- [NEEDS CLARIFICATION: should the shipped `publish.yml` set `UV_KEYRING_PROVIDER=disabled` in the
  publish job? It is already the default, so this guards only against a consumer that put
  `keyring-provider` in a committed file — which is the mistake most worth catching, since its
  symptom is "trusted publishing stopped working" with no error naming the cause. Against: config
  existing solely to neutralise other config is its own smell, and it ships to every consumer
  through `scaffoldapy`. Note this is now the only part of this plan that would touch a workflow at
  all, and it is a different decision from the plan's main question.]

- [NEEDS CLARIFICATION: what is the naming convention for the secret, and who owns it? A repository
  secret, an environment secret tied to the existing `pypi` GitHub Environment (whose reviewer rule
  is already the real gate on the irreversible step), or an organisation secret. The environment
  variant composes with the protection rule already designed and is probably right, but it has not
  been priced. Unanswerable in the abstract — it wants a real target.]

- [NEEDS CLARIFICATION: helm's CI path, the one case where the documented rule does not fully hold.
  `helm registry login --password-stdin` keeps the secret off the command line and out of the
  process table, but writes it into helm's registry config on the runner — a file, which is the
  thing the rule says not to create. Whether that matters on an ephemeral runner, or whether the
  tool's login should be bypassed entirely, needs deciding rather than assuming. Recorded in
  `release-workflows.md` as deliberately undecided.]

## Recommended direction

Nothing further until a real non-OIDC target exists. The first question above is separable and could
be answered now on its own merits; the other two cannot be answered honestly without a target to
answer them about, and guessing produces configuration nobody validated.

When a target does arrive, do helm's case last — it is the one whose fallback still writes a file,
and the only one where the answer might be "do not use the tool's login at all".

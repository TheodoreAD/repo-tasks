---
status: idea
updated: 2026-09-10
---

# Pins that rot, and a checker with a floor

## Context

Split out of `2026-08-28-node20-action-deprecation.md` on 2026-09-10, when that plan's own subject —
the family's Node 20 deprecation — was finished and retired. Three things it had consciously scoped
out survived it, and they are one subject: **how these repos keep workflow action pins both safe and
current, on repos whose owner pushes straight to `main` and reviews no PRs.**

What already shipped, and is not re-opened here: `ci.status` prints a run's `warning`/`failure`
annotations, and `ci.check-actions` reports which `uses:` refs are behind, comparing only at the
precision the pin states. The settled decisions behind both — SHA-pin `publish.yml` and nothing
else, no dependabot, no schedule, report-only rather than auto-bumping, and the tool survey that
priced the alternatives — are in
[`../contributing/quality-gate.md`](../contributing/quality-gate.md) ("Workflow hardening" and
"Nothing here runs on a schedule"). Read that before re-litigating any of it; this plan is only
about what those decisions left open.

## Open questions

### Does `ci.check-actions` make pinning-everywhere maintainable after all?

[NEEDS CLARIFICATION: the SHA-pin decision weighed exactly two options — pin everywhere and let the
pins rot, or pin everywhere plus dependabot and take a PR stream nobody reads. `ci.check-actions` is
a third option that decision did not have: a checker that reports a stale pin without opening a PR.
Whether that is enough to carry hash pins across every workflow, or whether "someone remembers to
run it" is the same rot in a different place, is unmeasured. The honest test is how long a known
stale pin actually survives here — `security-reusable.yml`'s consumer pins are the live specimen.]

The pins that exist today are `publish.yml`'s two `actions/checkout` sites and each consumer's
`security-reusable.yml` ref. That second set already has a known hole, recorded in
`quality-gate.md`: `_latest_tag` reads GitHub Releases, this repo publishes tags and no Releases, so
a consumer's pin to this repo goes stale invisibly. Pinning more workflows widens whatever that hole
turns out to cost.

### The checker cannot tell a truthful pin comment from a lying one

[DEFERRED: `ci.check-actions` reads a SHA pin's version out of its trailing `# v7.0.1` comment and
never checks that the comment is _true_ — a comment naming one version beside a SHA that is
something else reads as current. `pinact` does verify this. It was not worth a Go-binary install
method in `setup.toml` on its own, but the check has a floor and this is it. A cheap in-house
version is one `gh api repos/<action>/git/ref/tags/<version>` call per SHA pin, which is the same
call a human makes when re-resolving one by hand.]

### Nobody has measured how often a major actually bites

[UNVERIFIED: the argument for report-only over auto-bumping rests on the claim that the expensive
half of a bump is reading the major's release notes and deciding whether its breaking change reaches
these repos. That is true of the work done so far, but nothing has measured the _rate_. The sample
is small and one-sided: across `checkout` v5/v6/v7, `setup-python` v6/v7, `setup-uv` v10 and
`login-action` v4, exactly one (setup-uv v10's cache defence) had a breaking change worth checking
in detail and none of them bit. A sample of seven majors with zero hits does not distinguish "the
reading is load-bearing" from "the reading is a ritual" — and if it is the latter, the case for a
tool that edits the file gets stronger, not weaker.]

## Recommended direction

Rough, and deliberately not started:

1. **Answer the measurement question before the pinning one.** If majors in this family reliably
   reach nothing, both the report-only design and the pinning-everywhere question change shape. The
   data is already in git — each bump commit here records what was read and whether it applied.
2. **Fix the checker's floor before widening its remit.** Verifying a pin comment against the ref is
   a small addition to a task that already asks GitHub for each action; widening pinning while the
   checker can be lied to is the wrong order.
3. **Treat the reusable-workflow pin as the pilot.** It is the one pin in the family with a known
   invisible-staleness hole, it belongs to this repo, and whatever answer works for it is the answer
   for pinning everywhere.

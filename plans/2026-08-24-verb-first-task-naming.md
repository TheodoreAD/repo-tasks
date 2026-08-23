---
status: idea
updated: 2026-08-24
depends_on: [power-user-linux-setup]
---

# Verb-first task naming for the shared namespaces

## Context

`power-user-linux-setup/plans/2026-08-24-invoke-task-naming-convention.md` settled a family-wide
convention: **the namespace is the subject, the task is the action**, so `inv <namespace>.<task>`
reads as an imperative — "apt: install base", "zsh: fix history". Community conventions win over
formal consistency (`status`, `list`, `version` stay as they are), and multi-word task names lead
with the verb except where an object-first pair reads as a family in `inv --list`
(`format-check`/`format-apply`).

That plan carved out `quality.*`, `configs.*`, `docs.*` and `dev-env.*` as belonging here, and is
**blocked on this follow-up existing** — its own words: "the split below is sequencing, not an
exemption, and this plan is not `landed` until the follow-up exists." Per `~/AGENTS.md`'s cross-repo
rule the convention is mandatory family-wide, not optional per repo.

This plan is that follow-up. It did not exist while `repo-tasks` was actively renaming tasks on
2026-08-24, which is how the conflict below got created rather than avoided.

## Open questions

[NEEDS CLARIFICATION: the new `test` namespace inverts the convention, and it was named by the user
directly. `inv test.unit` / `test.smoke` / `test.regression` / `test.all` put the **verb in the
namespace** and the **object in the task** — the exact mirror of "namespace is the subject, task is
the action". Read as `<namespace>.<task>` it is "test: unit", not "unit: test".

Three ways out, and this is a real trade-off rather than an oversight to correct:

1. **Keep it.** `inv test.unit` reads naturally as an imperative sentence and matches how the user
   asked for it. Argue that `test` is a legitimate verb-namespace and the convention's "subject"
   means "the subject area", which `test` is.
2. **Invert to fit the rule** — `unit.test`, `integration.test` — which nobody would want, and which
   splits one facility across four namespaces.
3. **Fold back into `quality`** as `quality.test-unit`/`quality.test-integration`, which does obey
   the rule (subject `quality`, verb-first compound `test-unit`) but was explicitly moved away from
   this session for good reasons: four-plus test targets crowding the quality namespace, and
   `quality` already owning lint/format/type/shell.

Option 1 with the convention amended to admit verb-namespaces for a facility whose whole purpose is
one action looks strongest, but that is an amendment to the other repo's plan, not a decision this
one can take alone.]

[NEEDS CLARIFICATION: what else in this package violates the rule? A first read of `inv --list`
suggests `docs.build`/`docs.serve`/`docs.clean`, `configs.pull`/`configs.diff`,
`quality.lint-check`/`lint-apply`/`format-check`/`format-apply`, `deps.lock`/`check`/`list`/`tree`/
`export`, `venv.sync`/`create`/`delete`/`install-wheel`, `dist.build`/`publish`/`versions` and
`gitflow.*` are already verb-first or covered by the community-convention exception. `dev-env.setup`
is verb-first. Needs an actual audit against the rule rather than this impression, including whether
`format-check`/`format-apply` is one of the object-first families the convention explicitly allows.]

[NEEDS CLARIFICATION: `repo-tasks.version`/`.status`/`.update`/`.stamp` — `version` and `status` are
community conventions and stay, but is `stamp` a verb here (write the stamp file) or a noun? It
reads as a verb, so probably fine.]

## Recommended direction

Audit `inv --list` against the rule, land whatever renames it turns up in one pass, and settle the
`test` namespace question with the other repo's plan rather than unilaterally — that plan cannot
reach `landed` until this one resolves, so the two want deciding together.

No deprecation burden either way: this package has no consumers yet, which is why the test-task
rename this session shipped without a shim.

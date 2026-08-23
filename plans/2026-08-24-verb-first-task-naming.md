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
2026-08-24 — which turned out not to matter for the names chosen, but is why they were chosen
without reference to a convention that already covered them.

## Open questions

[DECISION: `test.unit`/`test.integration`/`test.smoke`/`test.regression`/`test.all` **already
conform**. Resolved 2026-08-24 by reading the committed convention rather than the plan's summary of
it — `power-user-linux-setup/CONTRIBUTING.md`'s "Naming a task" rule 3 says: "Some namespaces are
themselves the action (`setup`, `verify`, `clean`, `deploy`). There the leaf names the scope or
object instead: `verify.all`, `clean.caches`, `deploy.all`." `test` is exactly such a namespace, and
`test.all` mirrors `verify.all`/`deploy.all` literally.

There was never a conflict; the earlier reading of this as an inversion came from the naming plan's
"namespace is the subject, task is the action" summary line, which rule 3 is the stated exception
to. The only change wanted upstream is listing `test` among rule 3's examples so the next reader
doesn't repeat the same misreading.]

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

Audit `inv --list` against the rule and land whatever renames it turns up in one pass. The `test`
namespace question is settled (it conforms), so the only thing this owes the other plan is the audit
result — that plan cannot reach `landed` until this one resolves.

No deprecation burden either way: this package has no consumers yet, which is why the test-task
rename this session shipped without a shim.

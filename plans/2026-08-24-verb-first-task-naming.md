---
status: landed
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

## Audit result (2026-08-24)

67 tasks in `inv --list`. Three names violated the rule; two more entries turned out not to be tasks
at all.

### Renamed

| current              | becomes                   | why                                                      |
| -------------------- | ------------------------- | -------------------------------------------------------- |
| `agents.claude-hook` | `agents.wire-claude-hook` | noun leaf; its own docstring already starts "Wire"       |
| `dist.versions`      | `dist.list-versions`      | noun leaf; its own docstring already starts "List"       |
| `configs-promote`    | `configs.promote`         | top-level noun-verb; pairs with `configs.pull`'s subject |

`configs.promote` moves into the shipped `configs` collection _locally_ — repo-tasks' own `tasks.py`
adds it with `ns.collections["configs"].add_task(...)`, so it still never ships in the package (see
`configs.py`'s note on why consumers must not get it), but it reads as one subject with two opposed
verbs: `pull` is package → root, `promote` is root → package.

### Two tasks that were never meant to exist

`inv --list` also showed `quality.unit`, `dev-env.allow`, `dev-env.create` and `dev-env.claude-hook`
— none of them declared. `Collection.from_module` adds _every_ `Task` object it finds in a module's
namespace, so a task imported for a `pre=` chain gets republished under the importing module's name.
`quality.py` imports `testing.unit`; `dev_env.py` imports all three of its prerequisites.

[PITFALL: an imported task is a published task. `from .testing import unit` in `quality.py` gave
`inv quality.unit` as a second name for `inv test.unit`, and `dev_env.py`'s three `pre=` imports
gave `dev-env.create`/`dev-env.allow`/`dev-env.claude-hook` as second names for tasks owned by
`venv`/`direnv`/`agents`. Nothing declared them and no test caught them — they only show up by
reading `inv --list` against the module sources. Fix: give any module that imports a task an
explicit module-level `ns = Collection(...)`, which `Collection.from_module` prefers over its
auto-scan.]

This matters beyond tidiness: `power-user-linux-setup` had documented `inv dev-env.claude-hook` in
`docs/claude-code.md` (including a heading) and `tests/README.md` — a command whose entire existence
was an accident of an import statement. Those now point at `agents.wire-claude-hook`.

### Conforming — recorded so nobody "fixes" them

- **`gitflow.feature-start`/`feature-finish`/`release-*`/`hotfix-*`/`support-*`** — object-first,
  and deliberately so: this is git-flow's own CLI naming (`git flow feature start`). Rule 2's
  community-convention clause covers it, and the pairs are exactly the object-first family rule 1
  carves out.
- **`quality.format-check`/`format-apply`/`lint-check`/`lint-apply`/`shell-format-*`** — the
  object-first family the convention names explicitly.
- **`quality.shell-check`/`type-check`, `deps.check`, `configs.diff`, `deps.list`,
  `repo-tasks.status`, `repo-tasks.version`** — rule 2.
- **`deps.tree`** — a direct `uv tree` wrapper, named after the subcommand it wraps. Rule 2.
- **`repo-tasks.stamp`** — `stamp` is the verb (write the stamp file), resolving this plan's own
  earlier question.
- **`test.*`** — rule 3, as already decided above.
- Everything else already leads with a verb.

## Landed

All three renames plus the two accidental-task fixes are in, `inv quality.precommit` green (199
tests). `power-user-linux-setup`'s own plan is unblocked.

[PITFALL: running this repo's gate from another repo's session needs its venv on `PATH`, not just an
absolute `inv` path. `~/AGENTS.md`'s documented cross-repo form —
`cd <repo> && <repo>/.venv/bin/inv <task>` — is not sufficient here, because the quality tasks shell
out to bare `pytest`/`ruff`, which resolve from `PATH` and so came from the _calling_ repo's venv.
The visible symptom was `ImportError: cannot import name 'helm' from 'repo_tasks'` pointing at
`power-user-linux-setup/.venv/lib/.../repo_tasks/__init__.py` — the consumer's _installed_ copy, not
this working tree. `cd <repo> && PATH=<repo>/.venv/bin:$PATH <repo>/.venv/bin/inv <task>` is the
form that works. Note the failure only appeared once type-check passed and the run got as far as the
unit tier; two earlier runs stopped at pyright and looked like ordinary type errors.]

## Migrated to

- **`contributing/task-module-conventions.md`**, under "Import siblings as
  `from .sibling import name`" — the `Collection.from_module` trap, extended onto the convention
  that causes it rather than given a section of its own.
- **`power-user-linux-setup/skills/invoke-task-conventions/`** — the naming rules themselves and the
  cross-repo evidence, including this audit's conforming-on-purpose cases (`gitflow.*` mirrors
  `git flow feature start`; `deps.tree` wraps `uv tree`).
- The PATH-prefix pitfall is now in `~/AGENTS.md`'s "Running a command against a different repo"
  rule, with its evidence in `power-user-linux-setup/contributing/global-agents-md.md`.

Not migrated, deliberately: the rename table and the audit's pass/fail listing of all 67 tasks.
`inv --list` is the live answer and `git log` has the before.

Ready to delete — its only inbound reference is
`power-user-linux-setup/plans/2026-08-24-invoke-task-naming-convention.md`, which is itself queued
for retirement.

---
status: landed
updated: 2026-08-25
---

## Context

`contributing/` was created by the now-retired plan-retirement pass, populated by migrating the
durable content out of six retiring plans. Migration can only carry across what those plans actually
contained, which is less than the four files' stated scopes describe.

This plan tracked those gaps. It existed because the alternative — leaving "TODO: document recovery"
lines inside the `contributing/` files — is the exact failure mode the plan-docs convention forbids:
prose has no status field, so nothing ever prompts a return visit.

## Resolution (2026-08-25)

Every gap has a home:

- **`versioning.md` — pre-release versions.** Direction decided: solve it for real (dev and rc
  builds across all three formats), not restrict to `X.Y.Z`. Design and open questions live in
  `plans/2026-08-25-prerelease-versions.md`; `versioning.md` points there.
- **`release-flow.md` — recovery from bad states.** All four written up under "Known bad states and
  how to get out". Two became guard clauses in `gitflow.py`, per the "stop loudly" convention:
  `_require_merged_pr` (finalize before the PR merged — which used to tag and push the wrong commit
  silently) and `_require_tag_absent` (a `sync/<tag>` PR closed unmerged, caught at the next
  `*_start`). The abandoned-branch and wrong-commit-tag states are documentation only: nothing in
  the flow can detect them, and the PR merge itself stays a human step a team cannot automate.
- **`test-tiers.md`** — resolved 2026-08-23 (clean-OS tests landed with their fixture sections).
- **`task-module-conventions.md`** — coherence pass done 2026-08-25 (three rules corrected against
  the code).
- **Index.** `CONTRIBUTING.md` at the repo root is the nexus — the per-file one-liners moved there
  from `AGENTS.md`, which now points at it; `README.md` links it. GitHub reads a root
  `CONTRIBUTING.md` natively, and the name does not collide with the `contributing/` directory.

## Migrated to

- `contributing/release-flow.md` — the four recovery procedures, the `[PITFALL:` on pre-guard
  finalize runs, the `[DECISION:` on stateless guards.
- `src/repo_tasks/gitflow.py` + `tests/unit/test_gitflow.py` — the two guards.
- `CONTRIBUTING.md`, `AGENTS.md`, `README.md` — the index.
- `plans/2026-08-25-prerelease-versions.md` — the versioning design question, as an open plan.

Not migrated: the original per-gap `[NEEDS CLARIFICATION:` wording — each is either answered above
or restated in the pre-release plan. Nothing deferred remains here.

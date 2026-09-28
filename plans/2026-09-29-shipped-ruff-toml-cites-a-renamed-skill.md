---
status: landed
updated: 2026-09-29
source_repo: github.com-personal/agent-skills
source_session: c7d58945-4709-4fa6-9253-1140af86d9c0.jsonl
source_moment: 2026-09-29
source_plan:
---

# The shipped `ruff.toml` cites a skill path that was renamed

## Context

The `TRY003` ignore in the shipped `ruff.toml` cites
`skills/python-conventions/references/rationale.md §3`. That skill was renamed
`python-conventions-taudelta` in agent-skills on 2026-09-27, so the path no longer exists.
agent-skills had already corrected its own copy by hand; `configs.pull` on 2026-09-29 put the stale
path back, since the pulled file is verbatim.

## Evidence

`inv configs.diff` in agent-skills, 2026-09-29, showed the line going from
`skills/python-conventions-taudelta/references/rationale.md` (current) to
`skills/python-conventions/references/rationale.md` (pulled).

## Recommended direction

Update the comment in the shipped copy to the new name, and name the repo too (`agent-skills`'
`skills/python-conventions-taudelta/…`), since in every consumer but agent-skills a bare `skills/`
path points at nothing. Worth a grep of the shipped configs for other `skills/<old-name>` citations
from the same rename.

## Migrated to

Nothing needed a new home. Fixed 2026-09-29 in `9435863`, in the shipped `ruff.toml` and this repo's
pulled copy, naming `agent-skills` as recommended; §3 of that rationale still covers exception
hierarchies. A grep of `src/repo_tasks/configs/` found no other `skills/` citation. Consumers get it
through the next release and sweep, like any shipped-config change — agent-skills' `configs.diff`
will show the line moving to the form it already hand-corrected.

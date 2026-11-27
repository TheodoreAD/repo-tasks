---
status: idea
updated: 2026-11-08
---

# release.create takes a notes file

## Context

Found 2026-11-08 while building agent-skills' `release-herald` skill, which drafts release notes
from every PR and commit since the previous release and writes them to a markdown file.

`inv release.create` (`src/repo_tasks/release.py:107-134`) accepts the notes only as
`--notes
"<md>"`, shell-quoted into `gh release create --notes`. A drafted body is long markdown
full of backticks, `$` and quotes, which is exactly what does not survive being passed as one shell
argument. `gh release create` already takes `--notes-file`/`-F`. The title is also fixed to the tag,
and `.github/workflows/release.yml` has no notes input at all.

Measured the same day: repo-tasks' own releases v0.3.0–v0.6.0 have bodies that are only a compare
link, because `--generate-notes` lists PRs and this repo pushes straight to `main`. `release-herald`
collected v0.5.0→v0.6.0 as 42 commits, 15 user-facing, every one with an adequate or rich body — the
material for real notes exists, the task just has no way to take it in.

## Recommended direction

- `release.create --notes-file <path>`, mutually exclusive with `--notes` and `--generate-notes`,
  passed through as `gh release create --notes-file`.
- `--title`, defaulting to the tag as today.
- Optionally a `notes-file` input on `release.yml` reading a path committed on the branch — or leave
  CI on `--generate-notes` and treat a drafted file as a local-only path; decide when implementing.

`release-herald` itself calls `gh release create` directly with the same guards (tag on the remote
via `--verify-tag`, refusal when a release exists), so this is not blocking it; it is what lets the
repo's own task be the one that ships a curated body.

---
status: idea
updated: 2026-11-27
source_repo: personal/nexus
source_session: 34294f1e-3eff-4138-9e6f-91db7335af4d.jsonl
source_moment: 2026-11-27
source_plan:
---

# Windows quoting and shipped config bugs

## Context

Findings from two sessions that were about to close: the repo-tasks v0.8.0 release session
(repo-tasks-0a) and an ataraxia session that measured repo-tasks' shipped configs (ataraxia-9e). Not
yet reproduced by a session working in repo-tasks.

### Windows quoting bug in `release.push-tag`

`src/repo_tasks/release.py:66`, `_require_tag_on_branch`: on Windows, cmd.exe keeps the single
quotes in `--format='%(refname:short)'`, so the guard refuses a tag that really is on main. Still
present on `main` at `e59c7cf` (checked 2026-11-27).

**The same quoting is in a second place the fix must cover:** `src/repo_tasks/gitflow.py:54`
(`git for-each-ref --format='%(refname:short)' refs/heads/release/*`), pinned by
`tests/unit/test_gitflow.py:16`; `tests/unit/test_release.py:98` pins the release one. **The quotes
are there on purpose:** `contributing/release-flow.md:184` says the format must stay single-quoted
because bash breaks on the bare parentheses, so the fix has to satisfy both shells and that doc line
changes with it. Double quotes do (`--format="%(refname:short)"`: bash keeps `%(...)` literal,
cmd.exe strips the quotes and leaves a lone `%` unexpanded); not yet tried on either. When fixed,
also update `plans/2026-09-06-windows-support.md`, whose premise "No machine in this family runs
Windows" no longer holds. Separately, `inv quality.check` on a Windows checkout has 29 failing unit
tests, all Windows-only; they also fail at v0.7.2, and CI passes on Linux.

### Shipped-config bugs (measured on ataraxia)

1. **pytest `anyio_mode`** — `pytest.ini` keeps `anyio_mode` whenever `uv.lock` contains AnyIO, even
   when only an optional group pulls it in, so pytest stops with "Unknown config option" in a
   dev-only venv
2. **basedpyright `extraPaths: ["."]`** — switches off basedpyright's automatic src lookup, so a
   src-layout app without `py.typed` gets "missing type stubs" warnings for its own package
3. **`configs.pull` shadows repo config** — silently shadows a repo's `[tool.ruff]`,
   `[tool.basedpyright]` and `[tool.pytest.ini_options]`
4. **ruff `extend` and banned-api** — `extend` replaces the parent's banned-api table instead of
   merging it (tested by that session)

### Related, in other repos

- Done: scaffoldapy dropped the `~/.cache/claude-code` e2e assertion in `5d81543` (2026-11-26) and
  swept to v0.8.0 in `157caf7`
- Done: power-user-linux-setup dropped wire-claude-hook from `docs/tasks.md` in `cc86ee4`

## Evidence

Cross-session wrap-up messages received in the nexus session above on 2026-11-27, from repo-tasks-0a
("one question is still waiting on the user … release.py:66") and ataraxia-9e ("Four bugs: (a)
pytest.ini keeps anyio_mode …"). The user had not yet said whether to file the quoting bug; it is
filed here so it isn't lost when those sessions close.

## Open questions

- Pass git arguments as a list (no shell), or double quotes that both shells read the same? Double
  quotes keep `c.run` and the tests' exact-string pins; a list would mean leaving `c.run` for those
  two calls.
- Onboard ataraxia onto repo-tasks partially (dev dependency plus venv/deps/ci tasks), or only after
  the config redesign below?

## Recommended direction

Fix the push-tag quoting first: it blocks releasing from Windows. For the config bugs, consider the
design idea from the ataraxia measurement: `configs.pull` writes the shipped base files to
`.repo-tasks/`, root configs inherit from them (ruff `extend`, basedpyright `extends`, dprint
`extends`) with a repo layer on top, and pytest extras come from a `[pytest]` table in
`repo-tasks.toml`. That would supersede
`plans/2026-09-29-consumer-pyright-tier-and-subtree-include.md`.

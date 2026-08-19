---
status: idea
updated: 2026-08-19
---

## Context

`repo_tasks` distributes shared config for every tool this family's `quality.py` wraps — `ruff`,
`basedpyright`, `pytest`, `dprint`, `shellcheck`/`shfmt` — to every consumer repo (see
`power-user-linux-setup/plans/2026-08-14-python-repo-scaffolding.md` §D for the distribution
mechanism, `configs.pull`/`configs.diff`/`configs.local.toml`). Two of those tools' actual
relationship with `.gitignore` were checked empirically while designing that mechanism, and the
result was not what documentation-only reasoning would have predicted:

- **`ruff` respects `.gitignore` natively, no config needed.** Confirmed live against
  `power-user-linux-setup`: `ruff check .` surfaces 0 hits from the (gitignored) `reference/` tree;
  explicitly targeting `ruff check reference/` (bypassing normal file discovery) surfaces 143.
  `ruff.toml` carries no manual exclude for it.
- **`basedpyright` does NOT respect `.gitignore`.** Confirmed live: stripping
  `power-user-linux-setup`'s `reference`/`skills/*/references/snippets` exclude entries (down to just
  basedpyright's own default exclude list) took the same codebase from `0 errors, 2811 warnings` to
  `132 errors, 3509 warnings` — entirely from the gitignored `reference/` tree and standalone example
  snippets getting type-checked. Needs permanent, explicit excludes.

`pytest`, `dprint`, `shellcheck`, `shfmt` (and `fd`, which several leaf tasks already shell out to for
file discovery — `quality.py`'s `_sh_files`) haven't been checked at all yet — their behavior is
currently assumed, not verified, and the ruff/basedpyright split is direct evidence that assuming is
the wrong move here.

A related, second concern surfaced in the same discussion: rather than reactively discovering
repo-specific excludes one at a time (as happened for `power-user-linux-setup`'s
`cli-allowlist/help-cache`), it's worth preemptively covering the exclude paths the wider Python
ecosystem already converges on (`.venv`, `dist/`, `build/`, `*.egg-info`, `__pycache__`,
`.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.coverage`, `node_modules`, ...). The guiding
principle, stated directly: `.gitignore` should absorb as much of that complexity as possible — one
declaration, respected automatically by every tool that supports it — with a tool's own exclude list
reserved only for the paths that specific tool won't skip via `.gitignore` no matter what.

**Core tenet driving this whole plan, stated directly by the user and meant to generalize beyond
just this one file: reuse actively-maintained upstream work instead of rolling our own, wherever
one already exists.** Checked directly (2026-08-19) whether that upstream work already exists for
the ".gitignore content" half of this problem, rather than assuming `repo_tasks` should author a
Python `.gitignore` from scratch: **it does, and it's already the thing PyCharm itself is built on.**
PyCharm/IntelliJ's bundled `.ignore` plugin ([JetBrains/idea-gitignore on
GitHub](https://github.com/JetBrains/idea-gitignore), formerly `hsz/idea-gitignore`, now maintained
directly by JetBrains — the "New → .gitignore file" generator built into PyCharm/every JetBrains IDE)
generates its templates from **[github/gitignore](https://github.com/github/gitignore)** — GitHub's
own officially-maintained template repository — not a bespoke JetBrains list. Confirmed via the
plugin's own README, not inferred: "the main idea of the .ignore plugin is to provide an easy way for
creating .gitignore files using predefined templates provided by the official GitHub repository —
github/gitignore." This is strong, independent validation that `github/gitignore`'s
[`Python.gitignore`](https://github.com/github/gitignore/blob/main/Python.gitignore) (plus, if
relevant, its
[`Global/JetBrains.gitignore`](https://github.com/github/gitignore/blob/main/Global/JetBrains.gitignore))
is the right upstream to adapt from for the "canonical `.gitignore` baseline" open question below —
not something to author independently, and not a choice unique to this plan: it's the same source a
mainstream, widely-used IDE tool already delegates to instead of maintaining its own list.

## Open questions

- [NEEDS CLARIFICATION: does `dprint check`/`dprint fmt` respect `.gitignore` by default, or does it
  need explicit `excludes` entries for anything gitignored? Verify the same way ruff/basedpyright
  were — run against a gitignored probe file with and without an explicit exclude, diff the result —
  don't trust the docs alone given how wrong that would have been for basedpyright.]
- [NEEDS CLARIFICATION: does pytest's test collection ever walk into a gitignored directory on its
  own? pytest has no git integration that I'm aware of, so it likely needs explicit
  `testpaths`/`norecursedirs` regardless of `.gitignore` state either way — but not verified, and
  worth confirming rather than assuming.]
- [NEEDS CLARIFICATION: `shellcheck`/`shfmt` are invoked over whatever `_sh_files`'s `fd -e sh .` call
  returns — `fd` itself respects `.gitignore` by default, so this pair likely already inherits
  gitignore-awareness for free, with zero config of its own needed. Confirm this rather than assume
  it transfers automatically.]
- [NEEDS CLARIFICATION: for `basedpyright` — the one tool confirmed not to respect `.gitignore` — is
  there any config toggle that changes that (some linters/type-checkers ship a "respect VCS ignore"
  option), or is an explicit, permanent exclude list genuinely the only lever available?]
- [NEEDS CLARIFICATION: how much of the "community-standard excludes" set is already covered by (a)
  each tool's own sane defaults — recall `power-user-linux-setup`'s own §C4 gotcha: basedpyright's
  default `exclude` already includes `**/.*`/`**/node_modules`/`**/__pycache__`, and the bug was
  *replacing* that default rather than the default itself being insufficient — versus (b) genuinely
  needing to be added somewhere. The likely real fix in most cases is "never let a config replace a
  tool's already-sensible default list" rather than "add more excludes" — confirm per tool before
  assuming new rules are needed anywhere.]
- **Resolved 2026-08-19 — ownership, in full: `scaffoldapy` owns `.gitignore`, source of truth and
  updates both, not split.** Content: `github/gitignore`'s `Python.gitignore` (and possibly
  `Global/JetBrains.gitignore`), same upstream PyCharm's own bundled `.ignore` plugin generates from
  — seeded into `scaffoldapy`'s template, not authored by hand. Direct instruction, and the reasoning
  holds up: a split "one repo seeds it, another keeps it current" ownership is exactly the same
  divided-responsibility failure mode that let `repo-tasks`'s own config files silently stall at
  their initial-commit snapshot (see the sibling `power-user-linux-setup` plan §D) — single ownership
  avoids repeating that. Updates flow the same way any other `scaffoldapy` template file's would:
  through `copier update` against already-generated repos, currently deferred (per that same plan's
  §D) until `scaffoldapy` stabilizes on fresh-repo generation — acceptable because `.gitignore`
  content genuinely doesn't churn: essentially all the work is the one-time "build it out right the
  first time" pass, not an ongoing sync problem. `repo_tasks` does **not** distribute or own
  `.gitignore` in any form — no `configs.pull` involvement for this file.
- **`repo_tasks`'s role narrowed to warning, not owning or writing.** Since `repo_tasks`'s own tool
  configs (`ruff.toml` today, whatever the dprint/pytest/shellcheck audit above adds) silently assume
  certain paths are gitignored — that's the entire basis of "ruff needs zero manual excludes because
  `.venv`/`reference/` are gitignored" — a repo whose `.gitignore` is missing one of those paths
  breaks that assumption invisibly (ruff would start linting the entire `.venv`, e.g.) with no
  connection back to the actual cause. `repo_tasks` should be able to flag that interference — but
  it doesn't own `.gitignore`, so it can only warn, never write to or "fix" it itself. Two different
  shapes of check, deliberately not conflated:
  - **A small, fixed, always-run, hard-coded check** — worth coding directly, not left to agent
    judgment, because it's cheap, deterministic, and the failure mode it catches is severe and
    non-obvious to debug from the symptom alone: verify (`git check-ignore <path>`, or equivalent)
    that the short, fixed list of paths `repo_tasks`'s *own* gitignore-reliant tool behavior actually
    depends on (`.venv` today; whatever the dprint/pytest/shellcheck audit above adds) really are
    ignored in the calling repo. Same shape and same test discipline as every other leaf task in
    `quality.py` (`MockContext`-tested), folded into `configs.diff` (or a small dedicated task) —
    this is the one thing in this whole `.gitignore` question concrete enough to be "specific things
    important to check and warn about every time," per the instruction inviting that call.
  - **Everything broader — is this repo's `.gitignore` complete, does it match the current upstream
    `github/gitignore` template, should a new community-convention entry be adopted — is a skill-
    level, agent-judgment interaction, not code.** Matches the instruction directly: this is fuzzy,
    infrequent (`.gitignore` content "doesn't change often"), and benefits from an agent reading the
    actual diff and deciding, not a hard-coded rule silently applying itself. No specific mechanism
    designed yet — likely lands as guidance in whatever skill ends up pairing with `scaffoldapy`
    (already flagged as a to-be-built pairing in the sibling plan's §B), not a `repo_tasks` task.

## Recommended direction

Audit each remaining tool the same empirical way ruff/basedpyright already were: a gitignored probe
path containing a deliberately-flagged file, run the tool with and without an explicit exclude for
that path, diff the finding count. Record the confirmed result per tool — not assumed, not "per the
docs" — in a short reference table, promoted into this repo's own `README.md`/`AGENTS.md` once
resolved so the next tool added to `quality.py` gets checked the same way as a matter of course,
rather than this becoming a one-off audit that's never repeated.

Once each tool's real behavior is known: tools that already respect `.gitignore` get no manual
excludes for gitignored content (matches `ruff` today). Tools that don't get the minimum necessary
exclude list, scoped to content that's actually gitignored-or-equivalent, never as a substitute for
maintaining `.gitignore` itself — and always extending each tool's own default exclude list rather
than replacing it, per the `power-user-linux-setup` §C4 gotcha.

For the community-convention set: **`scaffoldapy` seeds its template `.gitignore` from
`github/gitignore`'s `Python.gitignore` rather than authoring one** (confirmed above as the same
upstream PyCharm's own bundled generator uses — reuse already-maintained work over rolling our own,
the core tenet this plan opened with) — this repo's own involvement stops at the fixed, hard-coded
"are the paths our tools depend on actually gitignored" check described above, not the file's
content or its ongoing currency. End state: `.gitignore` is the single place the community-standard
noise is declared, owned end-to-end by `scaffoldapy`, and only the tools this audit confirms
gitignore-blind need a short, explicitly-commented, parallel exclude entry of their own in
`repo_tasks`'s package data.

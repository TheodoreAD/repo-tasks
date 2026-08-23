---
status: idea
updated: 2026-08-24
depends_on: [scaffoldapy, power-user-linux-setup]
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
- [PITFALL: `basedpyright` does NOT respect `.gitignore`, unlike `ruff` right above it — so a
  gitignored tree is silently type-checked unless an explicit exclude names it.] Confirmed live:
  stripping `power-user-linux-setup`'s `reference`/`skills/*/references/snippets` exclude entries
  (down to just basedpyright's own default exclude list) took the same codebase from
  `0 errors, 2811 warnings` to `132 errors, 3509 warnings` — entirely from the gitignored
  `reference/` tree and standalone example snippets getting type-checked. Needs permanent, explicit
  excludes.

`pytest`, `dprint`, `shellcheck` and `shfmt` were unchecked when this plan was written — their
behavior assumed rather than verified, with the ruff/basedpyright split as direct evidence that
assuming is the wrong move. That audit has since been done; see "The audit, done" below.

A related, second concern surfaced in the same discussion: rather than reactively discovering
repo-specific excludes one at a time (as happened for `power-user-linux-setup`'s
`cli-allowlist/help-cache`), it's worth preemptively covering the exclude paths the wider Python
ecosystem already converges on (`.venv`, `dist/`, `build/`, `*.egg-info`, `__pycache__`,
`.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.coverage`, `node_modules`, ...). The guiding
principle, stated directly: `.gitignore` should absorb as much of that complexity as possible — one
declaration, respected automatically by every tool that supports it — with a tool's own exclude list
reserved only for the paths that specific tool won't skip via `.gitignore` no matter what.

**Core tenet driving this whole plan, stated directly by the user and meant to generalize beyond
just this one file: reuse actively-maintained upstream work instead of rolling our own, wherever one
already exists.** Checked directly (2026-08-19) whether that upstream work already exists for the
".gitignore content" half of this problem, rather than assuming `repo_tasks` should author a Python
`.gitignore` from scratch: **it does, and it's already the thing PyCharm itself is built on.**
PyCharm/IntelliJ's bundled `.ignore` plugin
([JetBrains/idea-gitignore on GitHub](https://github.com/JetBrains/idea-gitignore), formerly
`hsz/idea-gitignore`, now maintained directly by JetBrains — the "New → .gitignore file" generator
built into PyCharm/every JetBrains IDE) generates its templates from
**[github/gitignore](https://github.com/github/gitignore)** — GitHub's own officially-maintained
template repository — not a bespoke JetBrains list. Confirmed via the plugin's own README, not
inferred: "the main idea of the .ignore plugin is to provide an easy way for creating .gitignore
files using predefined templates provided by the official GitHub repository — github/gitignore."
This is strong, independent validation that `github/gitignore`'s
[`Python.gitignore`](https://github.com/github/gitignore/blob/main/Python.gitignore) (plus, if
relevant, its
[`Global/JetBrains.gitignore`](https://github.com/github/gitignore/blob/main/Global/JetBrains.gitignore))
is the right upstream to adapt from for the "canonical `.gitignore` baseline" open question below —
not something to author independently, and not a choice unique to this plan: it's the same source a
mainstream, widely-used IDE tool already delegates to instead of maintaining its own list.

## The audit, done (2026-08-23)

Measured per tool, against probe trees, not read off documentation. This is the reference table the
"Recommended direction" section asked for.

| tool               | respects `.gitignore`                      | additive exclude                                   | additive include               | config inheritance                  |
| ------------------ | ------------------------------------------ | -------------------------------------------------- | ------------------------------ | ----------------------------------- |
| ruff               | **yes**, `respect-gitignore` on by default | `extend-exclude`                                   | `extend-include`               | `extend`                            |
| dprint             | **yes**, plus `.git/info/exclude`          | `excludes` is already additive on top of gitignore | —                              | `extends`                           |
| shellcheck / shfmt | **inherited**, see below                   | n/a                                                | n/a                            | n/a                                 |
| pytest             | **no**                                     | `norecursedirs` **replaces** its default list      | `testpaths`                    | —                                   |
| basedpyright       | **no**, and rejected upstream              | **none** — open feature request                    | none, but see the glob finding | `extends`, top-level keys overwrite |

- **ruff.** Confirmed locally against ruff 0.16.3: a gitignored `generated/` directory produced zero
  findings with no `exclude` of any kind in `ruff.toml`, while the tracked `src/` file was flagged.
  An `extend-exclude` naming a directory that does not exist is not an error.
- **dprint.** Respects `.gitignore` and `.git/info/exclude` by default (`--no-gitignore` opts out);
  a gitignored file can be un-excluded with a negated glob. Git's _global_ excludes file is
  deliberately **not** respected unless `DPRINT_GLOBAL_GITIGNORE=1`, because it is machine-specific
  and would make CI disagree with a developer's machine. So `dprint.json`'s `excludes` only ever
  needs entries for **tracked** files that must not be formatted — `uv.lock` and the helm
  `templates/*.yaml` entries are exactly that, and neither could be expressed via `.gitignore`.
- **shellcheck / shfmt.** Both are invoked over whatever `quality.py`'s `_sh_files` returns, which
  is `git ls-files --cached --others --exclude-standard -- '*.sh'` — gitignore-aware by
  construction, since `--exclude-standard` is git's own ignore handling. Nothing to configure.
  [PITFALL: this plan previously described `_sh_files` as calling `fd -e sh .`. It does not, and has
  not for some time. The conclusion happened to be the same (gitignore-aware for free) but for the
  wrong reason — a reminder that a plan is not evidence about current code.]
- **pytest.** No git integration. `norecursedirs` has a default list (`.*`, `build`, `dist`, `CVS`,
  `_darcs`, `{arch}`, `*.egg`, `venv`) and **setting it replaces that default** — the same trap as
  basedpyright's `exclude`. `testpaths` is the include-shaped lever and is the one to reach for.
- **basedpyright.** No `.gitignore` support, and pyright rejected the idea on the grounds that
  source-control configuration and tool configuration have different semantics
  ([pyright#129](https://github.com/microsoft/pyright/issues/129)). There is no `extend-exclude`; it
  is an open request ([pyright#10795](https://github.com/microsoft/pyright/issues/10795)). So for
  this one tool an explicit list genuinely is the only lever — which is precisely why its include
  list should be doing the work instead.

### Two basedpyright findings that contradict its own documentation

[PITFALL: setting `exclude` **replaces** basedpyright's documented defaults (`**/node_modules`,
`**/__pycache__`, `**/.*`), and the documentation's further promise that "pyright also excludes any
virtual environment directories regardless of the exclude paths specified... cannot be overridden"
does **not** hold. Measured: with `include: ["**/src"]` and `exclude: ["tests/integration"]`, a
probe analysed `.venv/lib/python3.13/site-packages/dep/src/` and `node_modules/thing/src/` — and
still did so after adding a real `pyvenv.cfg` **and** declaring `venvPath`/`venv` explicitly.
Restating the three defaults alongside the real exclude fixed it. Any `exclude` this family ships
must restate them.]

[PITFALL: an `include` entry that is a **literal** path which does not exist is a hard config error
— exit 3, `File or directory "..." does not exist`, printed alongside an otherwise clean summary
line. An `include` entry that is a **glob** matching nothing is fine. Measured both ways. This is
the entire reason `configs.py`'s `_resolve_content` filters the include list per consumer, and the
reason that filtering causes the ratchet described in
`plans/2026-08-23-configs-round-trip-divergence.md`.]

Note the live contradiction this leaves in the repo: `pyrightconfig.json`'s own comment claims
"basedpyright silently no-ops on whichever entries don't exist in a given repo, so one shared list
works everywhere with nothing to adjust per consumer." That is false for `include`, and
`configs.py`'s docstring states the opposite correctly. The comment should go.

## Rule of thumb: includes, not excludes

[DECISION: excludes do not belong in tool configs outside `.gitignore`, as a default posture. An
exclude list is brittle in a way an include list is not — it goes wrong the moment somebody adds a
directory, and nobody remembers to update it, whereas a new directory simply isn't picked up by an
include-shaped config until someone opts it in. Stated 2026-08-23.]

How far each tool can actually honour that, given the audit above:

- **ruff, dprint, shellcheck/shfmt** — fully. `.gitignore` does the work; the only excludes that
  remain are for _tracked_ files that must not be touched (`uv.lock`, helm `templates/*.yaml`),
  which `.gitignore` cannot express by definition.
- **pytest** — fully, via `testpaths` instead of `--ignore`/`norecursedirs`. See
  `plans/2026-08-23-test-tiers-and-dependency-groups.md`.
- **basedpyright** — the rule holds here too, and more easily than it first appeared. A narrow
  include list needs no excludes at all: `["src", "tests", "tasks", "tasks.py"]` never reaches
  `.venv`, which is why this repo has never leaked despite carrying an exclude that replaces the
  defaults. The apparent tension — that covering a workspace member's nested `src/` seemed to need a
  recursive `**/src`, which _does_ reach into `.venv` and forces excludes back in — turned out to be
  false. **A directory include is already recursive**: measured, a literal `examples` entry reaches
  `examples/svc/src/svcpkg/c.py`. Named directories cover nested layouts with no glob and no
  exclude, so `**/src` is simply not needed.

## Open questions

- [NEEDS CLARIFICATION: given that directory includes are recursive, the only remaining reason to
  prefer globs is that a literal entry **hard-errors when absent** while a glob matching nothing is
  fine — the sole cause of `configs.pull`'s per-consumer filtering and its ratchet
  (`plans/2026-08-23-configs-round-trip-divergence.md` §1a). Is there a glob spelling of each
  canonical entry that tolerates absence _without_ widening reach — `examples`, `tests`, `tasks`
  each expressed so they match only a top-level directory of that name? If yes the filtering can be
  deleted outright, root and package go byte-identical, and the ratchet disappears with no merge
  mechanism. Not yet tested; the highest-leverage measurement left.]
- [NEEDS CLARIFICATION: is basedpyright's `extends` a better distribution mechanism than copying the
  file at all? A consumer's `pyrightconfig.json` could be three lines extending the canonical copy
  shipped inside the installed `repo_tasks` package. Blockers to check: `extends` resolves relative
  paths against the config file's own location, and the docs say nothing about pointing into an
  installed package; the path would also vary by environment. If it works it dissolves the whole
  pull/promote round trip for this one file — the highest-leverage thing on this list.]
- [NEEDS CLARIFICATION: how much of the "community-standard excludes" set is already covered by (a)
  each tool's own sane defaults — recall `power-user-linux-setup`'s own §C4 gotcha: basedpyright's
  default `exclude` already includes `**/.*`/`**/node_modules`/`**/__pycache__`, and the bug was
  _replacing_ that default rather than the default itself being insufficient — versus (b) genuinely
  needing to be added somewhere. The likely real fix in most cases is "never let a config replace a
  tool's already-sensible default list" rather than "add more excludes" — confirm per tool before
  assuming new rules are needed anywhere.]
- [DECISION: `scaffoldapy` owns `.gitignore` outright — source of truth and updates both, not split
  (resolved 2026-08-19).] Content: `github/gitignore`'s `Python.gitignore` (and possibly
  `Global/JetBrains.gitignore`), same upstream PyCharm's own bundled `.ignore` plugin generates from
  — seeded into `scaffoldapy`'s template, not authored by hand. Direct instruction, and the
  reasoning holds up: a split "one repo seeds it, another keeps it current" ownership is exactly the
  same divided-responsibility failure mode that let `repo-tasks`'s own config files silently stall
  at their initial-commit snapshot (see the sibling `power-user-linux-setup` plan §D) — single
  ownership avoids repeating that. Updates flow the same way any other `scaffoldapy` template file's
  would: through `copier update` against already-generated repos, currently deferred (per that same
  plan's §D) until `scaffoldapy` stabilizes on fresh-repo generation — acceptable because
  `.gitignore` content genuinely doesn't churn: essentially all the work is the one-time "build it
  out right the first time" pass, not an ongoing sync problem. `repo_tasks` does **not** distribute
  or own `.gitignore` in any form — no `configs.pull` involvement for this file.
- [DECISION: `repo_tasks` warns about `.gitignore` interference, never owns or writes the file.]
  Since `repo_tasks`'s own tool configs (`ruff.toml` today, whatever the dprint/pytest/shellcheck
  audit above adds) silently assume certain paths are gitignored — that's the entire basis of "ruff
  needs zero manual excludes because `.venv`/`reference/` are gitignored" — a repo whose
  `.gitignore` is missing one of those paths breaks that assumption invisibly (ruff would start
  linting the entire `.venv`, e.g.) with no connection back to the actual cause. `repo_tasks` should
  be able to flag that interference — but it doesn't own `.gitignore`, so it can only warn, never
  write to or "fix" it itself. Two different shapes of check, deliberately not conflated:
  - **A small, fixed, always-run, hard-coded check** — worth coding directly, not left to agent
    judgment, because it's cheap, deterministic, and the failure mode it catches is severe and
    non-obvious to debug from the symptom alone: verify (`git check-ignore <path>`, or equivalent)
    that the short, fixed list of paths `repo_tasks`'s _own_ gitignore-reliant tool behavior
    actually depends on (`.venv` today; whatever the dprint/pytest/shellcheck audit above adds)
    really are ignored in the calling repo. Same shape and same test discipline as every other leaf
    task in `quality.py` (`MockContext`-tested), folded into `configs.diff` (or a small dedicated
    task) — this is the one thing in this whole `.gitignore` question concrete enough to be
    "specific things important to check and warn about every time," per the instruction inviting
    that call.
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

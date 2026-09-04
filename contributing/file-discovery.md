# File discovery and `.gitignore`

Which of the tools `quality.py` wraps skip gitignored content on their own, which are blind to it,
and why the shipped configs are include-shaped rather than carrying exclude lists. Extracted from
the now-retired `plans/2026-08-19-gitignore-tool-alignment.md`; the one question it left open is
`plans/2026-09-05-pyright-include-coverage.md`.

The guiding principle: **`.gitignore` absorbs as much of this as it can** — one declaration,
respected automatically by every tool that supports it — and a tool's own exclude list is reserved
for what that tool will not skip via `.gitignore` no matter what.

## The rule: includes, not excludes

[DECISION: excludes do not belong in tool configs outside `.gitignore`, as a default posture. An
exclude list is brittle in a way an include list is not — it goes wrong the moment somebody adds a
directory and nobody remembers to update it, whereas a new directory simply is not picked up by an
include-shaped config until someone opts it in. Stated 2026-08-23.]

`contributing/test-tiers.md` applies the same rule to `pytest.ini`'s `testpaths`, and
`pyrightconfig.json`'s `include` is the rule's other main instance.

## Three ways a tool gets gitignore-awareness

Measured per tool against probe trees, not read off documentation — the ruff/basedpyright split
below is direct evidence that reading the docs would have got it wrong.

| tool                                  | respects `.gitignore`                      | additive exclude                                   | additive include |
| ------------------------------------- | ------------------------------------------ | -------------------------------------------------- | ---------------- |
| ruff                                  | **yes**, `respect-gitignore` on by default | `extend-exclude`                                   | `extend-include` |
| dprint                                | **yes**, plus `.git/info/exclude`          | `excludes` is already additive on top of gitignore | —                |
| shellcheck, shfmt, actionlint, zizmor | **by construction** — see below            | n/a                                                | n/a              |
| pytest                                | **no**                                     | `norecursedirs` **replaces** its default list      | `testpaths`      |
| basedpyright                          | **no**, and rejected upstream              | **none** — open feature request                    | see below        |

### 1. The tool does it itself

**ruff** respects `.gitignore` natively with no config. Confirmed against `power-user-linux-setup`:
`ruff check .` surfaces 0 hits from its gitignored `reference/` tree, while `ruff check reference/`
— bypassing normal file discovery — surfaces 143. Confirmed again locally against ruff 0.16.3: a
gitignored `generated/` directory produced zero findings with no `exclude` of any kind, while the
tracked `src/` file was flagged. An `extend-exclude` naming a directory that does not exist is not
an error.

**dprint** respects `.gitignore` and `.git/info/exclude` by default (`--no-gitignore` opts out); a
gitignored file can be un-excluded with a negated glob. Git's _global_ excludes file is deliberately
**not** respected unless `DPRINT_GLOBAL_GITIGNORE=1`, because it is machine-specific and would make
CI disagree with a developer's machine. So `dprint.json`'s `excludes` only ever needs entries for
**tracked** files that must not be formatted — `uv.lock` and the helm `templates/*.yaml` entries are
exactly that, and neither could be expressed via `.gitignore`.

### 2. This package hands the tool its file list

`projects.py`'s `tracked_files()` runs `git ls-files --cached --others --exclude-standard` and every
file-gated step feeds on it: `quality.py`'s `_sh_files` (shellcheck, shfmt) and `_workflow_files`
(actionlint, zizmor), and `docs.py`'s listing. `--exclude-standard` is git's own ignore handling, so
gitignore-awareness here is a property of **this package**, not of any of those four tools — none of
them needs configuring for it, and a tool added to a file-gated step inherits it for free.

The same call also picks up untracked-but-not-ignored files, which is what lets a step see a file
written a moment ago and never `git add`ed.

[PITFALL: an earlier version of this audit described `_sh_files` as calling `fd -e sh .`. It did
not, and had not for some time. The conclusion happened to be the same — gitignore-aware for free —
but for the wrong reason. Read the code before describing what a discovery step does.]

### 3. The tool is blind, and the include list does the work

**pytest** has no git integration. `norecursedirs` has a default list (`.*`, `build`, `dist`, `CVS`,
`_darcs`, `{arch}`, `*.egg`, `venv`) and **setting it replaces that default** — the same trap as
basedpyright's `exclude`. `testpaths` is the include-shaped lever and the one to reach for; see
`contributing/test-tiers.md`.

**basedpyright** has no `.gitignore` support, and pyright rejected the idea on the grounds that
source-control configuration and tool configuration have different semantics
([pyright#129](https://github.com/microsoft/pyright/issues/129)). There is no `extend-exclude`
either; it is an open request ([pyright#10795](https://github.com/microsoft/pyright/issues/10795)).
So for this one tool an explicit list genuinely is the only lever — which is exactly why its
**include** list does the work instead.

## Why the shipped `pyrightconfig.json` needs no `exclude` at all

The obvious worry is that a venv contains directories named `src`, so an include naming `src` would
walk straight into it. Measured, it does not: **a bare `src` include names the top-level `./src`,
not "any directory called src"**. A probe with `include: ["src"]` and a plain nested `sub/src/d.py`
(no dot, no `pyvenv.cfg`, no exclude of any kind) analysed only `src/a.py`. The same probe with
`include: ["src", "tests", "tasks", "tasks.py"]` and **no `exclude` key at all** analysed exactly
one file, with both a dotted `.venv/lib/pkg/src/` and a dotless `venv/lib/pkg/src/` sitting there
untouched.

That is robust rather than lucky: it does not depend on the `**/.*` default catching a leading dot,
which would miss a venv named `venv/`. A **directory include is already recursive** — a literal
`examples` entry reaches `examples/svc/src/svcpkg/c.py` — so nested layouts need no glob and no
exclude.

The one thing that breaks it is a recursive glob. `**/src` genuinely does reach into a venv, which
forces excludes back in, and is why it is not used.

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
line. An `include` entry that is a **glob** matching nothing is fine, but only when the glob is in
the **last** segment: measured 2026-08-25 (basedpyright 1.39.10), `tests/**`, `tests/*` and
`./tests` all still exit 3 when `tests/` is absent, while `tests*` exits 0. `tests*` stays top-level
anchored (a probe with `.venv/lib/pkg/tests`, `venv/lib/pkg/tests` and `node_modules/x/tests`
analysed nothing) and is recursive once it matches; `tasks*` covers both `tasks/` and `tasks.py`.
That spelling is what the shipped config uses.]

[DECISION: the canonical `include` entries are spelled `src*`/`tests*`/`tasks*` — the trailing `*`
is the only spelling that tolerates absence without widening reach — so the list is uniform across
every consumer and `configs.pull` filters nothing per repo. The widening is confined to top-level
siblings sharing the prefix, and no repo in the family has one. Resolved 2026-08-25.]

[PITFALL: `--outputjson` **swallows the exit-3 config error**. The identical config that exits 3
with a `File or directory "..." does not exist` line on stdout exits **1** under `--outputjson`,
with nothing in the JSON to indicate a config problem. Anything consuming basedpyright's JSON — a CI
wrapper, a coverage check over the include list — cannot see config errors at all. A second layer of
the "clean output, wrong exit code" trap.]

## Why `pyrightconfig.json` is copied, not `extends`-ed

The tempting shape is a three-line consumer config extending the canonical copy inside the installed
package, dissolving the pull/promote round trip for this one file. A time-boxed spike ran it
2026-08-30 (basedpyright 1.39.10 / pyright 1.1.412) against a scratch consumer, and every claim here
is a measured run.

[DECISION: keep copying the file. `extends` inherits **rule settings** correctly — every severity,
and `pythonVersion`, which a child scalar overrides — but **not the two blocks that decide what gets
checked**, so the consumer has to re-declare exactly the parts whose absence is undetectable. What
it would save is the rule list; what it would cost is a silent failure mode the copy has never had.]

[PITFALL: **relative paths inside the extended config resolve against the extended file's own
directory, not the extending one**, and the failure is silent-green. With only `"extends"` in the
consumer's config, `include: ["src*", "tests*", "tasks*"]` resolved inside the package's `configs/`
directory: `filesAnalyzed: 0`, exit 0 — a consumer that type-checks nothing and passes its gate.
Proved causal: a file dropped at `<package>/configs/src/oops.py` was analysed from the consumer's
working directory. `executionEnvironments[].root` resolves the same way and fails the other
direction, checking the consumer's tests under the full profile. So the consumer's file must carry
`extends`, the whole `include` list _and_ the whole `executionEnvironments` block — the two largest
structures in the file, and the two carrying the most rationale.]

[PITFALL: a broken `extends` path does not abort. basedpyright prints
`Config file "..." could not be read.` and **continues with default settings**, silently discarding
the profile (`reportAny` degraded to warning, `failOnWarnings` gone). It exits 3, so CI catches it;
an editor's language server does not. And the path is the part that varies — pointing into a venv
embeds the interpreter version, which breaks on the next floor bump.]

## `.gitignore` itself is not this package's file

[DECISION: `scaffoldapy` owns `.gitignore` outright — source of truth and updates both, not split
(resolved 2026-08-19). `repo_tasks` does **not** distribute or own it in any form; it is absent from
`configs.py`'s `_CONFIG_FILES` and from the package's `configs/` directory. A split "one repo seeds
it, another keeps it current" ownership is the same divided-responsibility failure that let this
repo's own config files stall at their initial-commit snapshot.]

[DECISION: the content is seeded from [`github/gitignore`](https://github.com/github/gitignore)'s
`Python.gitignore`, not authored by hand — the same upstream PyCharm's own bundled `.ignore` plugin
([JetBrains/idea-gitignore](https://github.com/JetBrains/idea-gitignore)) generates from, per its
own README. Reuse actively-maintained upstream work rather than rolling our own. Confirmed
2026-08-19, from the plugin's README rather than inferred.]

The consequence for this package looked like a dependency it cannot see: the shipped configs assume
certain paths are gitignored — that assumption is the entire basis of "ruff needs zero manual
excludes" — so a consumer whose `.gitignore` is missing one of them would break that assumption
invisibly, with no connection back to the cause. The one path this package's own behaviour depends
on is `.venv`, and the assumption turns out to hold there by construction.

[DECISION: **no `git check-ignore` gate step for `.venv`, because the venv ignores itself.**
Measured 2026-09-05: `uv venv` writes `.venv/.gitignore` containing `*`, and so does Python 3.14's
stdlib `venv`. In a scratch repo with no root `.gitignore` at all, `git check-ignore .venv/` and
`.venv/pyvenv.cfg` both report ignored via that nested file, and
`git ls-files --others --exclude-standard` lists nothing from the venv — so `tracked_files()`, ruff
and dprint never see it whatever the root file says. `venv.create` only ever uses uv. A gate step
checking the root entry would therefore pass in every consumer for a reason unrelated to their
`.gitignore`: nearly inert, which is the worse answer for the same decision — the same shape
`plans/2026-08-30-deferred-gate-tools.md` measured for the bandit subprocess rules, which cannot see
the `c.run` calls this package shells out through. A venv created by a tool that does not
self-ignore is the only case left, and none of this family's tooling can produce one.]

The wider question — is a repo's `.gitignore` complete, does it match upstream `github/gitignore`,
should a new community entry be adopted — is agent judgement rather than code: fuzzy, infrequent,
and better served by reading the actual diff than by a hard-coded rule. It belongs with
`scaffoldapy`, which owns the file.

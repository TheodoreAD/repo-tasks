---
status: idea
updated: 2026-08-30
depends_on: [scaffoldapy]
---

# What is left of the `.gitignore` alignment work

## Context

The audit this plan existed to run is **done**, and its results are no longer here. Migrated
2026-08-30 to [`../contributing/file-discovery.md`](../contributing/file-discovery.md): the per-tool
table (which tools respect `.gitignore`, which are blind, which get it from this package's own
`tracked_files()`), the includes-not-excludes rule of thumb, the four confirmed basedpyright
pitfalls, the measurement showing a narrow include list needs no `exclude` at all, and the two
ownership decisions (`scaffoldapy` owns `.gitignore`, seeded from `github/gitignore`).

Deliberately **not** migrated: everything below. It is either unbuilt or undecided, and
`contributing/` describes what is true now.

One thing the migration corrected rather than copied. This plan's audit recorded gitignore-awareness
for shellcheck and shfmt as a property of `quality.py`'s `_sh_files`. That helper is now
`projects.py`'s `tracked_files()`, shared by shellcheck, shfmt, actionlint, zizmor and `docs.py` —
so it is a named package-level mechanism, and the two workflow tools added since the audit inherited
the property without anyone deciding they should. That is the right outcome, but it happened
silently, which is the same shape as the gap the first open question below describes.

## The one concrete thing still unbuilt

[DECISION: `repo_tasks` warns about `.gitignore` interference, never owns or writes the file. Its
own tool configs silently assume certain paths are gitignored — that is the entire basis of "ruff
needs zero manual excludes" — so a repo whose `.gitignore` is missing one of them breaks that
assumption invisibly, with no connection back to the cause. But this package does not own the file,
so it can only warn.]

The check, as designed and still unwritten: verify with `git check-ignore` that the short fixed list
of paths this package's own gitignore-reliant behavior depends on (`.venv` today) really are ignored
in the calling repo. Small, deterministic, always-run, hard-coded — worth coding rather than leaving
to agent judgment, because it is cheap and the failure it catches is severe and non-obvious from the
symptom alone. Same shape and same `MockContext` test discipline as every other leaf task in
`quality.py`, folded into `configs.diff` or given a small task of its own.

[DECISION: everything broader — is this repo's `.gitignore` complete, does it match current upstream
`github/gitignore`, should a new community-convention entry be adopted — is agent judgment, not
code. Fuzzy, infrequent, and better served by an agent reading the actual diff than by a hard-coded
rule applying itself. Likely lands as guidance in whatever skill ends up pairing with `scaffoldapy`,
not as a `repo_tasks` task.]

## Open questions

[NEEDS CLARIFICATION: should anything detect a source tree no `include` entry covers? A check that
every tracked `*.py` file is matched by some entry would catch a new top-level tree the moment it
appears — the exact gap `examples/sample-service` sat in before it moved under `tests/`. Same shape
as the fixed `git check-ignore` check above, and the two probably want to be one task. Moved here
from the now-retired `plans/2026-08-23-configs-round-trip-divergence.md`.]

[NEEDS CLARIFICATION: is basedpyright's `extends` a better distribution mechanism than copying the
file at all? A consumer's `pyrightconfig.json` could be three lines extending the canonical copy
shipped inside the installed `repo_tasks` package. Blockers to check: `extends` resolves relative
paths against the config file's own location, and the docs say nothing about pointing into an
installed package; the path would also vary by environment. If it works it dissolves the whole
pull/promote round trip for this one file — the highest-leverage thing on this list. Note this got
harder, not easier, since it was written: `configs.py` now derives `pythonVersion` per consumer
(`c514bd9`), so an `extends` shape would need somewhere to put a derived value that the canonical
copy cannot carry.]

[NEEDS CLARIFICATION: how much of the "community-standard excludes" set is already covered by each
tool's own sane defaults, versus genuinely needing to be added somewhere? The likely real answer is
"never let a config replace a tool's already-sensible default list" rather than "add more excludes"
— which is what the basedpyright and pytest findings in the migrated audit both say. Confirm per
tool before assuming any new rule is needed.]

## Recommended direction

The `git check-ignore` check is the only part of this worth building on its own, and it is small. Do
it together with the include-coverage question above if both are wanted, since they are one task
wearing two hats: both ask "is a path this repo cares about actually visible to the tools that
should see it".

The `extends` question is the one with real leverage and real risk of being a dead end; time-box a
spike rather than designing it.

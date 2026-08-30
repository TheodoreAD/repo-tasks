---
status: idea
updated: 2026-08-30
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

[NEEDS CLARIFICATION: how much of the "community-standard excludes" set is already covered by each
tool's own sane defaults, versus genuinely needing to be added somewhere? The likely real answer is
"never let a config replace a tool's already-sensible default list" rather than "add more excludes"
— which is what the basedpyright and pytest findings in the migrated audit both say. Confirm per
tool before assuming any new rule is needed.]

## The `extends` spike: answered, and the answer is no

Time-boxed spike run 2026-08-30, basedpyright 1.39.10 / pyright 1.1.412, against a scratch consumer
whose `pyrightconfig.json` extends a copy of this package's `configs/pyrightconfig.json` sitting at
a path standing in for site-packages. Every claim below is a measured run, not the documentation.

The hoped-for shape was a three-line consumer config extending the canonical copy shipped inside the
installed package, dissolving the pull/promote round trip for this one file. It does not work, and
the way it fails is worse than not working.

[DECISION: keep copying the file. `extends` inherits **rule settings** correctly but **not the two
blocks that decide what gets checked**, so the consumer has to re-declare exactly the parts whose
absence is undetectable. What it would save is the rule list; what it would cost is a new silent
failure mode the copy has never had.]

What does inherit, confirmed working:

- Every rule severity. `reportAny` fired as an **error** in the extending project, its shipped
  value, not basedpyright's default of warning.
- `pythonVersion`. A `type Alias = int` statement in the consumer drew
  `Type alias statement requires Python 3.12 or newer` from the inherited `"3.11"`.
- A child scalar overrides the parent: setting `"pythonVersion": "3.13"` in the extending file
  cleared that error. **So the derived-value blocker this plan worried about is not a blocker** —
  `configs.py`'s per-consumer `pythonVersion` would go in the child, which is the natural place for
  a derived value anyway. That is the one thing the spike found in `extends`' favour.

[PITFALL: **relative paths inside the extended config resolve against the extended file's own
directory, not the extending one** — and the failure is silent-green. With only `"extends"` in the
consumer's config, `include: ["src*", "tests*", "tasks*"]` was resolved inside the package's
`configs/` directory: `filesAnalyzed: 0`, exit 0. A consumer in that state type-checks **nothing**
and its gate passes. Proved causal rather than inferred — dropping a file at
`<package>/configs/src/oops.py` made basedpyright analyze _that_ file, from the consumer's working
directory, and report its `reportAny` errors.]

[PITFALL: `executionEnvironments[].root` resolves the same way, and fails in the opposite direction.
The shipped `root: "tests"` relaxation pointed at a `tests/` beside the packaged config, so the
consumer's own tests were checked under the full profile — `reportUnusedFunction` came back as an
error on a test helper, which is red on correct input. Re-declaring the `executionEnvironments`
block verbatim in the extending file cleared it, confirming the cause.]

Together those two mean the consumer's file must carry `extends`, the whole `include` list, **and**
the whole `executionEnvironments` block — the two largest structures in the file and the two
carrying the most rationale in their comments. The inheritable remainder is the flat rule list.

[PITFALL: a broken `extends` path does not abort — basedpyright prints
`Config file "..." could not be read.` and **continues with default settings**, silently discarding
the entire profile (`reportAny` degraded from error to warning, `failOnWarnings` gone). It does exit
3, so CI catches it; an editor's language server or a local run whose exit code nobody reads does
not. This matters because the path is the part that varies: pointing into a venv means embedding the
interpreter version, `.venv/lib/python3.11/site-packages/...`, which breaks on the next floor bump.]

## Recommended direction

The `git check-ignore` check is the only part of this worth building on its own, and it is small. Do
it together with the include-coverage question above if both are wanted, since they are one task
wearing two hats: both ask "is a path this repo cares about actually visible to the tools that
should see it".

The `extends` question is closed — the spike above ran and the answer is to keep copying the file.
What is left of this plan is the `git check-ignore` check, the include-coverage question it pairs
with, and the per-tool excludes confirmation. None of the three has real leverage; this plan is a
candidate for retirement once the check is either built or consciously dropped.

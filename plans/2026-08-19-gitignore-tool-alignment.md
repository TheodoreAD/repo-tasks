---
status: landed
updated: 2026-09-05
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

## Resolved 2026-09-05: the check is dropped on measurement, and the plan retires

The `git check-ignore` check below was the last thing this plan proposed building, and it was
measured before being written: `uv venv` and Python 3.14's stdlib `venv` both write a `.gitignore`
containing `*` inside the venv, and git honours it with no root entry at all — `check-ignore`
reports `.venv/` ignored, `ls-files --others --exclude-standard` lists nothing from it.
`venv.create` only uses uv, so the one path this package depends on being ignored is ignored by
construction, and the check would pass everywhere for a reason unrelated to the consumer's
`.gitignore`. Nearly inert is the worse answer for the same decision; the measurement and the
decision are in `contributing/file-discovery.md`, "`.gitignore` itself is not this package's file".

The two open questions:

- The include-coverage check is a different question — pyright is blind to `.gitignore`, so its
  include list is the only lever — and it is the one live thing this plan leaves. Filed as its own
  idea, `plans/2026-09-05-pyright-include-coverage.md`, with the instance that motivated it.
- The per-tool excludes question is answered by the audit that already migrated: the basedpyright
  and pytest findings in `file-discovery.md` both say a config must never replace a tool's default
  exclude list, and no new rule was needed for any tool surveyed.

## Migrated to

- [`../contributing/file-discovery.md`](../contributing/file-discovery.md) — the audit (2026-08-30);
  now also the `.venv` self-ignore measurement and the decision not to build the check, and the
  `extends` spike as "Why `pyrightconfig.json` is copied, not `extends`-ed", compressed to the
  decision and the two pitfalls a future proposer would need.
- `plans/2026-09-05-pyright-include-coverage.md` — the include-coverage question.

Deliberately not migrated: the check's own design paragraph below, which describes a thing that is
now decided against, and the spike's list of what does inherit, which only matters if `extends` is
ever reconsidered — `archive --search extends` brings it back.

## The one concrete thing that was still unbuilt, as designed

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

Retire. The check was consciously dropped on measurement, the `extends` question closed with the
spike, and the include-coverage question has its own plan.

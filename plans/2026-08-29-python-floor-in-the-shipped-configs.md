---
status: in-progress
updated: 2026-08-30
---

# The shipped canonical configs decide every consumer's Python floor

## Context

The household rule, restated by the user 2026-08-29 and now explicit about both ends:

> **3.11 is the floor** for `repo-tasks`, for libraries, and for anything other people may need to
> run on their own machines — skills and MCP servers included. **Applications start on 3.14.**

An application controls its own runtime, so it may use whatever syntax that runtime supports.
Anything someone else installs into their own project does not, and 3.11 is where that floor sits.

The design question — how a project declares which tier it is in — is owned by
`ingesta/plans/2026-08-29-python-version-floors.md`, which named `repo-tasks` as the thing to check
first: "it runs the tools; it does not decide what they target. Anything in it that hardcodes a
version is the thing to find first — if it does, that is the actual blocker, because every consumer
inherits it."

It does. This plan is that half.

## What this repo actually ships

`configs.py`'s `_CONFIG_FILES` sync is byte-identical-file-per-consumer by design, and two of those
files carry the floor:

| shipped file                 | as diagnosed               | effect on a consumer                         |
| ---------------------------- | -------------------------- | -------------------------------------------- |
| `configs/ruff.toml`          | `target-version = "py311"` | pinned every consumer to 3.11 syntax — fixed |
| `configs/pyrightconfig.json` | no `pythonVersion`         | checks against whatever interpreter is found |

Measured here 2026-08-29, in a scratch project, both directions:

- **ruff infers the floor from `requires-python` when `target-version` is absent.** A file using
  `def identity[T](value: T) -> T` passes under `requires-python = ">=3.12"` and fails under
  `>=3.11` — same `ruff.toml`, only the pyproject line changed. So the pin is not carrying its
  weight: deleting it makes each consumer's own declared floor the answer, with the file still
  byte-identical everywhere.
- **basedpyright does not.** Same tree, `requires-python = ">=3.11"`, the same PEP 695 file: 0
  errors, 0 warnings. It uses the interpreter it finds. Independently reproduces the disagreement
  `ingesta`'s plan measured.

[PITFALL: the declared floor is enforced today by exactly one of the two tools, by accident. Every
consumer of this package inherits both halves — a ruff pin nobody chose per project, and a type
checker validating against whichever venv happens to be active rather than against what the project
claims to support. The second is the same class of error as testing against a database you do not
deploy, and it is silent: the tool reports success.]

## Recommended direction

Rough; the pyright half is the part with a real trade-off.

1. ~~**Delete `target-version` from the shipped `configs/ruff.toml`.**~~ **Landed 2026-08-29.** One
   byte-identical file serves both tiers, because each consumer's `requires-python` already says
   which tier it is in. The deleted line is replaced by a comment saying why it is absent and what
   the one changed case is, so the next reader does not restore it as an oversight. `configs.pull`
   materialised it into this repo's own `ruff.toml` in the same commit; `ruff check --show-settings`
   here still resolves 3.11, now from `requires-python` rather than from the pin.
2. **Give basedpyright an explicit `pythonVersion`, derived at pull time from the consumer's
   `requires-python`** — route B below, **chosen 2026-08-30**. The tension that made this look
   expensive (per-project value, byte-identical shipped file) dissolves once derivation is
   distinguished from preservation; see the decision block after the routes table.
3. **Leave the tier question itself to `scaffoldapy`**, per the owning plan — a generation-time
   answer that fans out to `requires-python` and CI. Nothing here should grow its own notion of
   which tier a repo is in.

## The three routes for step 2

Measured 2026-08-29 on basedpyright 1.39.10, in the same scratch projects as the ruff probe:

- `basedpyright --pythonversion 3.11 probe.py` reports
  `error: Function type parameter syntax requires Python 3.12 or newer`. The same file with no flag
  is clean — it uses the interpreter it finds, which is 3.14 here. So the CLI flag works and is the
  cheapest lever available.
- **`[tool.basedpyright]` in `pyproject.toml` is ignored whenever a `pyrightconfig.json` exists.**
  `pythonVersion = "3.11"` in pyproject produced the 3.12 error with the shipped
  `pyrightconfig.json` removed and produced nothing with it present — same pyproject both times.
  This kills the tempting fourth route ("let each consumer declare it in its own pyproject next to
  `requires-python`"): it cannot coexist with the file this package ships.

| route                                   | shipped file stays byte-identical | editor agrees with CI |
| --------------------------------------- | --------------------------------- | --------------------- |
| A — `--pythonversion` from `quality.py` | yes                               | **no**                |
| B — derive `pythonVersion` at pull time | **no**                            | yes                   |
| C — library-tier venv _is_ the floor    | yes (no config change at all)     | yes                   |

- **A. `quality.py` reads `requires-python` and passes `--pythonversion`.** One source of truth, no
  per-repo file, nothing about `configs.py` changes. The cost is the row above: an editor's
  basedpyright LSP reads the config file alone and never sees the flag, so the IDE stays permissive
  while CI is strict. That is the failure mode this whole plan is about — a tool reporting success
  against the wrong version — merely moved from CI to the editor.
- **B. `configs.pull` writes `pythonVersion` into each consumer's `pyrightconfig.json`.** Editor and
  CI agree because the answer is in the file. The cost is that this one file stops being a
  byte-for-byte materialisation, so `configs.diff` has to apply the same derivation before comparing
  or it reports drift forever — and "why does this repo's config differ" gains a second possible
  answer, which is exactly the objection raised against a per-repo append in
  `2026-08-29-pytest-ini-anyio-mode.md`. The two questions should be answered the same way.
- **C. A library-tier repo's venv is 3.11.** basedpyright's found-interpreter default is then
  already correct and no config changes at all — the cheapest fix that has no editor/CI split. The
  cost is that dev runs the floor rather than the newest, and `venv.create` has to know which tier
  the repo is in, which is `scaffoldapy`'s question rather than this one. It also only helps the
  type checker: nothing else about the tier follows from it.

## The decision: route B, plus a per-run override

[DECISION: **route B — `configs.pull` derives `pythonVersion` from the consumer's own
`requires-python`.** Taken 2026-08-30. It is the only route where the editor and CI read the same
answer, which is the entire point of the plan; A explicitly fails that column and C buys it only by
making dev run the floor. The two objections that had it deferred both turned out to be weaker than
they read:

- **It is not blocked on `scaffoldapy`.** The tier question fans _out_ to `requires-python`, and
  `requires-python` is exactly what B reads — so B is correct before the tier mechanism lands and
  stays correct after, with nothing to redo. Only C genuinely needs the tier, because only C has to
  decide what a venv is built with. This plan's `depends_on: [scaffoldapy]` was removed on that
  basis.
- **Its cost is not the cost a per-repo append pays**, which is what
  `2026-08-29-pytest-ini-anyio-mode.md` assumed when it said the two should be decided together.
  Derivation and preservation are different mechanisms: a derived file is still fully determined by
  the canonical copy plus one declared input, so `configs.diff` applies the same derivation and
  still compares exactly, and "why does this repo's config differ" keeps a single answer — its
  `requires-python` differs. Preservation is the one that gives that question two answers and leaves
  `diff` nothing to check against. Both plans are answered the same way after all, just not with the
  mechanism either of them expected: **pulled configs are derived from declared facts about the
  consumer, never preserved hand-edits.**]

### The matrix case, which is what nearly forced a blunt answer

The objection raised against putting any floor in the config: a repo running a Python matrix in CI
wants static analysis at more than one version, and a config file holds one. Answered — **both tools
take a per-run override that beats the config**, measured 2026-08-30 on basedpyright 1.39.10 and
ruff 0.16.3, over `def identity[T](value: T) -> T`:

| run                                                          | result                                                                |
| ------------------------------------------------------------ | --------------------------------------------------------------------- |
| `pyrightconfig.json` pins `"pythonVersion": "3.11"`, no flag | `error: Function type parameter syntax requires Python 3.12 or newer` |
| same file, `basedpyright --pythonversion 3.12`               | 0 errors, 0 warnings                                                  |
| `requires-python = ">=3.11"`, no `ruff.toml`                 | `invalid-syntax: Cannot use type parameter lists on Python 3.11`      |
| same, `ruff check --target-version py312`                    | All checks passed                                                     |

So the floor lives in the config, where the editor can see it, and a matrix job overrides per entry.
`quality.type-check` and the ruff tasks grow an optional `--python-version` that forwards to each
tool's own flag.

[DECISION: **CI does not wire that flag in by default.** Static analysis checks source against the
_declared floor_, and the floor is one value however many interpreters the tests run on — a second
version only catches a `sys.version_info`-gated branch. Real, but narrow enough that paying for it
everywhere is the wrong default. The flag exists so a repo that wants it can ask; nothing in the
shipped workflow asks on its behalf. Taken 2026-08-30 under an explicit "simplicity first"
instruction.]

[PITFALL: `pyrightconfig.json` is JSONC and this repo's copy is roughly half comments, each one
carrying the rationale for a rule. Deriving a value into it must be a one-line rewrite of a
placeholder the canonical file already carries — parsing and re-dumping the JSON destroys every
comment, which is most of the file's value.]

## Open questions

**Answered 2026-08-29 (ruff 0.16.3), and the answer is "yes, in two directions at once."** Probed in
three scratch projects differing only in `requires-python`, each carrying the shipped `ruff.toml`
with the pin removed, over a file using PEP 695 `def identity[T](value: T) -> T`:

| `requires-python` | `ruff check` on PEP 695 | `linter.unresolved_target_version` | `formatter` / `analyze` |
| ----------------- | ----------------------- | ---------------------------------- | ----------------------- |
| `>=3.11`          | syntax error            | 3.11                               | 3.11                    |
| `>=3.12`          | clean                   | 3.12                               | 3.12                    |
| _field absent_    | clean                   | **none**                           | **3.10**                |

So a consumer with no `requires-python` does not fall back to one default — the linter falls back to
_no version at all_ and accepts the newest syntax, while the formatter and `analyze` fall back to
3.10. With the pin still in place that same consumer got 3.11 for all three (measured by overriding
`--config 'target-version="py311"'` in the same project), so the pin was doing real work in exactly
this one case and nowhere else. Deliberately not fixed by keeping the pin: a package with no
`requires-python` is broken independently of ruff, and the shipped comment now says so.

[NEEDS CLARIFICATION: a 3.11 floor for skills has a consequence the rule's wording does not settle.
`agent-skills` ships stdlib scripts run as bare `python3` on whatever the machine has — that
interpreter is 3.12 on Ubuntu 24.04 and 3.10 on 22.04, so a 3.11 floor is a claim about which
machines a skill runs on, not about what a dependency resolver will accept. Whether the rule means
"write 3.11 syntax" or "declare >=3.11 and stop supporting 22.04" is worth stating explicitly
wherever the rule ends up recorded.]

[NEEDS CLARIFICATION: this repo's CI already runs a 3.11–3.14 unit matrix
([`../contributing/quality-gate.md`](../contributing/quality-gate.md)) whose stated purpose is to
make `requires-python = ">=3.11"` true rather than aspirational. Whether a consumer in the
application tier should get a single-version matrix from the same template, or keep the range, is a
template question rather than this one — but the two answers have to agree.]

## Verification

The ruff half is verified **here**: `inv quality.precommit` green on the pulled file (471 tests),
and `ruff check --show-settings` reporting 3.11 from `requires-python` with no pin present. That is
the whole of what this repo can prove on its own.

It is **not** verified at a consumer, and cannot be yet: nothing reaches one until
`inv repo-tasks.update` moves the global tool, so a `configs.diff` run today compares against the
old package and reports "up to date" — indistinguishable from a real match. Left to the deferred
cross-repo sweep in `2026-08-25-consumer-transitions.md`, which owns that ordering.

**The basedpyright half landed 2026-08-30** (`b79b76a`, `c514bd9`, `db5d8d2`), verified here to the
same depth and no further:

- `configs.pull` derives `pythonVersion` from `requires-python`, omitting the key entirely when a
  project declares no floor — the ruff decision's shape, so neither tool imposes a floor nobody
  chose. `_diff_config_files` applies the same derivation, and a unit test pins the invariant that
  makes the whole thing work: a pull under a non-default floor followed by a diff reports up to
  date.
- Pulled into this repo's own root. `inv quality.precommit` green with basedpyright now checking at
  3.11 rather than the 3.14 interpreter it had been finding — 0 errors, 0 warnings, 489 tests — so
  nothing here was leaning on syntax above its own declared floor.
- `configs.promote` grew a guard in the same commit: the derived lines are restored to the package's
  own values before a root file is written back, so this repo's floor cannot become everyone's by
  the promote path. That was a hole the derivation itself opened.

[UNVERIFIED: that the editor half actually pays off — that a language server picks up the derived
`pythonVersion` and flags floor-violating syntax live. It follows from the value being in the config
file rather than on a command line, which is the documented difference between routes A and B, but
nothing here has watched an editor do it.]

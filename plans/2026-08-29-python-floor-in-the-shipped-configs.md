---
status: idea
updated: 2026-08-29
depends_on: [scaffoldapy]
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

| shipped file                 | today                      | effect on a consumer                         |
| ---------------------------- | -------------------------- | -------------------------------------------- |
| `configs/ruff.toml`          | `target-version = "py311"` | pins every consumer to 3.11 syntax           |
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

1. **Delete `target-version` from the shipped `configs/ruff.toml`.** Verified above to be the whole
   fix for ruff: one byte-identical file serves both tiers, because each consumer's
   `requires-python` already says which tier it is in. Cheapest, and independent of everything else
   here.
2. **Give basedpyright an explicit `pythonVersion`** — the bug fix `ingesta`'s plan already
   identified as landable on its own. The tension is that it is per-project while the shipped file
   is byte-identical. Options not yet weighed against each other: pyright's own `extends` (a small
   per-repo config extending the shipped base), a `configs.py` parameterization, or accepting that
   this one file stops being byte-identical.
3. **Leave the tier question itself to `scaffoldapy`**, per the owning plan — a generation-time
   answer that fans out to `requires-python` and CI. Nothing here should grow its own notion of
   which tier a repo is in.

## Open questions

[NEEDS CLARIFICATION: does dropping `target-version` change behavior for a consumer whose
`pyproject.toml` has no `requires-python` at all? ruff's fallback in that case was not probed, and a
consumer without the field would silently move to whatever the default is.]

[NEEDS CLARIFICATION: a 3.11 floor for skills has a consequence the rule's wording does not settle.
`agent-skills` ships stdlib scripts run as bare `python3` on whatever the machine has — that
interpreter is 3.12 on Ubuntu 24.04 and 3.10 on 22.04, so a 3.11 floor is a claim about which
machines a skill runs on, not about what a dependency resolver will accept. Whether the rule means
"write 3.11 syntax" or "declare >=3.11 and stop supporting 22.04" is worth stating explicitly
wherever the rule ends up recorded.]

[NEEDS CLARIFICATION: this repo's CI already runs a 3.11–3.14 unit matrix
(`2026-08-26-quality-tool-gaps.md` §11) whose stated purpose is to make `requires-python = ">=3.11"`
true rather than aspirational. Whether a consumer in the application tier should get a
single-version matrix from the same template, or keep the range, is a template question rather than
this one — but the two answers have to agree.]

## Verification

Not started. The ruff half is a one-line deletion plus a `configs.diff` run against both consumers,
which per the deferred cross-repo sweep will only measure anything after `inv repo-tasks.update`
moves the global tool.

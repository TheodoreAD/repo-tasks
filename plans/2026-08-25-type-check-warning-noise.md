---
status: idea
updated: 2026-08-25
---

# `quality.type-check` emits thousands of warnings on a green run

## Context

A passing `inv quality.precommit` in `power-user-linux-setup` prints ~1 MB: 4,145 basedpyright
warnings, 0 errors (measured 2026-08-25, basedpyright via the shared `pyrightconfig.json` in
`recommended` mode). By category:

| count | rule                         |
| ----: | ---------------------------- |
|  1195 | `reportUnknownMemberType`    |
|   674 | `reportUnknownVariableType`  |
|   633 | `reportUnknownArgumentType`  |
|   571 | `reportUnknownParameterType` |
|   497 | `reportMissingParameterType` |
|   150 | `reportPrivateUsage`         |
|   113 | `reportMissingTypeArgument`  |
|    93 | `reportUnknownLambdaType`    |
|    89 | `reportUnusedCallResult`     |
|    63 | `reportUnusedParameter`      |
|   ~70 | seven others, ≤27 each       |

`failOnWarnings` is `false`, so none of this gates anything; it is output nobody reads. The cost is
on agents: every session working in a consumer repo either pipes the gate through `| tail` (masking
the exit code — the failure `~/AGENTS.md`'s "Reading a command's result" rule exists for) or
redirects it to a log and reads that back (two calls, a prompt on a `$VAR` target), and the
`~/AGENTS.md` Bash rules had to be rewritten twice in two days around that habit. The habit is
rational while the output is 1 MB; the wording fix in `power-user-linux-setup`
(`contributing/global-agents-md.md`, "Composing a Bash call", 2026-08-25) says so and points here.

The `Unknown*` family (3,166 of 4,145) is almost entirely `invoke` flowing through untyped `Context`
parameters and `c.run()` results despite `allowedUntypedLibraries: ["invoke"]` — worth confirming
that setting does what the config comment claims for these rule categories.

## Open questions

- [NEEDS CLARIFICATION: is the `Unknown*` volume really invoke-sourced (check with a run restricted
  to a module with no `Context` use), or is it the repo's own untyped code — the fix differs: a
  config change for the former, a typing pass or per-rule downgrade for the latter.]
- [NEEDS CLARIFICATION: keep the diagnostics but stop printing them (basedpyright `--outputjson`
  into a file, print the summary line plus errors only), or downgrade the noisy `Unknown*`/
  `MissingParameterType` rules to `none` in the shared config? The first keeps the data for a future
  typing pass; the second is simpler and matches how every consumer actually treats them.]
- [NEEDS CLARIFICATION: `reportPrivateUsage` (150) — tests importing `_private` helpers is the
  repo-tasks/power-user-linux-setup test convention; add it to the `tests` execution environment's
  overrides like `reportUnusedFunction` already is?]

## Recommended direction

Make a green run print a one-line summary and nothing else, and a red run print errors only —
warnings go to a file (or nowhere) unless a `--warnings` flag asks for them. Whatever the mechanism,
the acceptance test is an agent-facing one: `inv quality.precommit` on a clean tree in
`power-user-linux-setup` must fit in a Bash tool result without truncation, so that no session has a
reason to pipe or redirect it.

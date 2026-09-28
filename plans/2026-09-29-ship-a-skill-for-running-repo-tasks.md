---
status: idea
updated: 2026-09-29
---

# Ship a skill for running repo-tasks' tasks

## Context

An agent working in a repo that consumes this package should know how to drive it: which task
answers an intent, how to read the gate's verdict, what a missing tool means. Today that reaches
agents two ways, both partial. A generated project's `AGENTS.md` (scaffoldapy's template) says "run
`inv dev-env.setup` once, `inv quality.precommit` before done", and `invoke-task-conventions` in
`agent-skills` covers _writing_ tasks, not running these ones.

The global rule "every skill on this machine is authored in `agent-skills`" blocked the obvious
home, so the question of where such a skill lives was researched first (2026-09-28/29, three passes
over local clones in `$RESEARCH_HOME`, the Claude Code plugin marketplaces and the MCP registry).
The full reports are attached below; the findings that decide the design:

- **Two populations, opposite answers.** Platform and service vendors keep skills in a dedicated
  repo — 227 of the 262 external plugins in Anthropic's official marketplace (87%). CLI tools whose
  skill describes their own commands keep it in the tool's repo, released with it: googleworkspace
  `gws`, gogcli, sentry-cli, playwright-cli, Prisma 8, mergify-cli, firecrawl, beads. Most generate
  it from the command tree and fail CI on a diff.
- **The one counter-example keeps the coupling.** JetBrains moved teamcity-cli's skill to its own
  repo so several products share one copy, then imported it as a pinned Go module and embeds it.
- **Drift is the observed failure of shipping separately.** beads #2493: generated guidance named a
  removed command. graphify #1568: a stale `uv tool` install beside a newer skill — the exact shape
  here, since this package is installed both as a uv tool and pinned per consumer in `uv.lock`, so
  two versions coexist on one machine.
- **Python has no ecosystem mechanism.** npm has TanStack Intent (422 packages), antfu's skills-npm,
  and a `skills sync` RFC on vercel-labs/skills opened 2026-09-28. Every Python tool found
  (comfy-cli, graphify, spec-kit, dstack) rolls its own install command over package data, and every
  copy-based installer grew staleness detection afterwards.
- **This machine had already decided it.** power-user-linux-setup's
  `plans/2026-08-26-agent-artifact-authoring-decoupling.md`, point 5: "Per-repo API skills live in
  the repo they describe, not in `agent-skills`… versioned with the code it documents." The global
  rule generalised from the convention skills and lost that exception, though `skill-authoring` kept
  it. Rewording the rule is filed for power-user-linux-setup; teaching `skill-authoring` how such a
  skill stays versioned with its tool is filed for `agent-skills`.

[DECISION: **The skill lives in this repo, versioned with the tasks it describes.** Every CLI found
whose skill documents its own commands does the same, and the one that moved out re-pinned it. A
separate repo gives the skill a second version axis, and this package already has two installs that
can disagree.]

[DECISION: **No MCP server.** Agents that use this package have a shell. beads measured its CLI plus
hooks at about 1-2k tokens against 10-50k for MCP schemas and ships MCP only for shell-less clients;
playwright-cli gives the same reason. Where a CLI does add MCP, the common shapes are a subcommand
or a sibling package, never a separate repo — so revisit as `repo-tasks mcp` if a shell-less client
ever needs it.]

[DECISION: **Discovery-first, no task catalogue in the skill.** invoke already describes itself:
`inv -l` lists every task with its docstring's first line and `inv --help <task>` gives flags. A
skill that names only the few entry points everything starts from, and sends the agent to those two
commands for the rest, cannot go stale against a rename. Same pattern as Backlog.md's
`backlog instructions` and beads' `bd prime`, the two designs in the research that cannot drift.]

## Open questions

[NEEDS CLARIFICATION: **Skill name and trigger boundary against `invoke-task-conventions`.** That
skill owns writing, naming and wiring tasks; this one owns running this package's tasks. The
description must name repo-tasks explicitly, or "which task should I use" goes to either. Check with
`skill-fitness` once drafted.]

[NEEDS CLARIFICATION: **Does it duplicate the consumer `AGENTS.md`?** The decoupling plan's own open
question. Probable split: `AGENTS.md` keeps the two always-needed lines, since a miss there is
silent and expensive; the skill carries what fires on a trigger. Settle during the pilot.]

[NEEDS CLARIFICATION: **Global install from a release tag or from HEAD?**
`npx skills add
TheodoreAD/repo-tasks#vX.Y.Z` pins to a tag (the skills CLI parses `#ref`,
`source-parser.ts`). Pinning keeps it matched to one version, but a consumer's `uv.lock` may pin
another, and with a discovery-first skill the difference is small. Whether `npx skills update`
respects a `#ref` is unverified.]

## Recommended direction

1. Draft `.agents/skills/<name>/SKILL.md`, which this repo already has with `.claude/skills` linked
   to it. That is where `skill-authoring` puts a skill documenting a repo's own interface (its
   "Publishing a skill repo" section): no install step for anyone working here, which makes the
   pilot free, and the skills CLI's discovery searches it for `npx skills add` from outside
   (`src/skills.ts:253-260` in vercel-labs/skills). Content, all version-stable:
   - the entry points: `inv dev-env.setup`, `inv quality.precommit`, `inv quality.check`, `inv -l`,
     `inv --help <task>`;
   - reading the gate: one line per step, the PASS/FAIL verdict, output shown whole on failure;
   - `command not found` means an unset-up repo, never `uv run inv`;
   - another repo's tasks: `inv -r` for machine-level tasks, `cd` plus `PATH` for toolchain ones;
   - tasks never wait for typed input;
   - the release flow's order, pointing at `contributing/release-flow.md` for the why.
2. Pilot it on this repo first, per the rule for anything shareable: use it for a session's real
   work and cut whatever turns out to be noise.
3. Give it a test in this repo's suite: frontmatter validates, and every `inv <task>` it names
   exists in `ns`. That is the whole staleness guard a discovery-first skill needs.
4. Install it globally through power-user-linux-setup's `setup.toml` — `[packages.agent-skills]`'
   `skills` list already takes several sources, so it is one entry.

[DEFERRED: **A pointer line in scaffoldapy's `template/AGENTS.md`** naming the skill, so generated
projects find it. After the pilot, filed for scaffoldapy rather than edited from here.]

[DEFERRED: **A generated task table or a copy-into-project install task.** Only if `inv -l` proves
insufficient in the pilot. If built: the generator runs in the gate and fails on a diff (gws,
sentry-cli), and an install task needs a version stamp and a check command from day one, since every
copy-based installer in the research grew one after shipping without it.]

## Attachments

- `skill-and-mcp-placement-research.md` — committed, 16 KB, attached 2026-09-29

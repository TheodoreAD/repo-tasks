# Making a change here reach consumers without breaking them

A push to `main` is a deploy. `bootstrap-repo-tasks.sh` is unpinned until a `vX.Y.Z` tag exists
(`selfinstall.stamp` refuses to pin to a tag that isn't real), so every consumer's next CI run
installs whatever `main` is at that moment — with no consumer-side action and no notice.

[PITFALL: a change to the shared tool list or the shipped configs is a breaking change for consumers
even when it is purely additive here. A consumer's `dependency-groups.dev` and its pulled config
files are snapshots taken whenever it was last bootstrapped; the gate that reads them is live.
Additive-here is subtractive-there until that consumer re-runs `ensure-deps` and `configs.pull`.]

This was measured twice in one day (2026-08-24/25), and both times the break was found from the
consumer side, hours later, by reading a red CI run:

- `quality.workflow-check` and its `actionlint-py` manifest entry landed together. Every consumer's
  `dev` group predated the entry, so CI failed with `actionlint: command not found` (exit 127) on
  every push until the next evening.
- `failOnWarnings: true` went into the shipped `pyrightconfig.json`. Every repo `scaffoldapy`
  generates pulls that config at generation time, and the template's own code carried twelve
  warnings — so all ten e2e combinations failed the moment the global tool moved to that commit.

## What counts as a consumer

A repo whose `tasks.py` does `from repo_tasks import ns`, or that carries a
`bootstrap-repo-tasks.sh`. Measured 2026-08-25 across `~/projects/github.com-personal`, there are
exactly two:

| repo                     | what it consumes                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------------ |
| `power-user-linux-setup` | the task collection and the shipped configs, in its own tree                                           |
| `scaffoldapy`            | the same, **plus** it bakes the configs into every repo it generates — see the two-gates pitfall below |

The five `*-polite-mcp` repos and `product-research-pipeline` are **not** consumers (no
`from repo_tasks`, no bootstrap script, no workflow running the gate). They predate the template and
are its migration backlog, not a sweep target.

The list is short enough that this file is the whole mechanism. A task that runs the sweep against
local checkouts earns its keep once those repos are regenerated onto the template, not before.

## When to sweep

After changing any of: the `repo-tasks-quality` manifest in `pyproject.toml`, anything under
`src/repo_tasks/configs/`, or a `quality.*` / `test.*` step that shells out to a binary.

## The sweep

Once, from anywhere — the tool install is global, not per-repo, so this is not part of the
per-consumer loop:

```shell
inv repo-tasks.update       # move the global uv tool install forward to what you just pushed
```

Then in each consumer's own checkout:

```shell
repo-tasks configs.diff     # what this consumer has drifted from — both configs and dev group
repo-tasks configs.ensure-deps
inv deps.lock               # re-resolve uv.lock; review the diff
inv venv.sync
inv configs.pull
inv quality.precommit       # the gate, against the new tool and the new configs
```

`configs.diff` is first for a reason: it reports both halves of the drift (stale config files _and_
`dependency-groups.dev` entries the manifest has grown), so it tells you which of the four steps
between it and the gate this particular consumer actually needs — often none, when the change was to
task code rather than to the manifest or the shipped configs. Run the gate regardless; that is what
says the new tool works here. `ensure-deps` is additive and idempotent — it never touches an entry
already present — so running it when nothing is missing costs nothing.

In `scaffoldapy`, `inv quality.precommit` is only half the sweep: finish with `inv test.integration`
(~80s), which renders every combination and runs the _generated_ repo's own gate. See the two-gates
pitfall below.

[PITFALL: `configs.pull` prints "pulled" for every file whether or not it wrote anything. Seen live
2026-08-25: a consumer's installed `repo_tasks` was still the pre-change commit, so the first pull
"pulled" the old config unchanged and looked successful. `inv repo-tasks.update` genuinely first,
and `configs.diff` to confirm, or the sweep silently does nothing.]

## Two lags, both invisible from a green terminal

- **The dev machine lags `main`.** The global `uv tool install` is whatever `inv repo-tasks.update`
  last fetched. A local gate can pass for a day against the old tool while CI runs the new one.
- **A user-wide binary masks a missing group entry.** `power-user-linux-setup` installs
  `actionlint`, `shfmt`, and friends onto `PATH` machine-wide, so a consumer whose `dev` group never
  declared them still passes locally and fails in CI, where only the group exists. This is what
  `require_tool`'s preflight message is worded for: it names the manifest entry, because the binary
  being on `PATH` is not evidence the group declares it.

[PITFALL: `scaffoldapy` is two things — a repo with its own gate, and a generator whose output has
its own gate. `inv quality.precommit` there is evidence about the first only. Only its e2e tier
(`inv test.integration`, ~80s, renders every combination and runs the generated `inv quality.check`)
tests the second, and it is the only thing in the family that does. Any "consumers verified" claim
has to name which of the two it ran, and against which repo-tasks commit — its e2e is evidence about
the global tool it rendered with (`inv repo-tasks.version`), not about `main`.]

## Still open

Whether `scaffoldapy`'s e2e becomes a pre-merge canary here (locally, or as a cross-repo CI job
bootstrapping repo-tasks from the PR's ref), and whether tagging a release — which would pin
consumers and turn each of these into a deliberate per-consumer update — is the better answer than
any of the above. Both in `plans/2026-08-25-consumer-transitions.md`.

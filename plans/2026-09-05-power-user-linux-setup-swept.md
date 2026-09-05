---
status: idea
updated: 2026-09-05
source_repo: github.com-personal/power-user-linux-setup
source_session: 25ea8788-b99d-43a2-9611-2d0c1f207694.jsonl
source_moment: 2026-09-05T18:00:00Z
---

# Half the batched sweep is done: `power-user-linux-setup` is on `7bb880b`

## Context

`plans/2026-08-25-consumer-transitions.md` deferred one batched sweep covering everything
accumulated here since `9d57d464`. **The `power-user-linux-setup` half of it ran on 2026-09-05**, 32
commits' worth, and this file is what that plan asked for: which way each prediction went, recorded
rather than assumed. `scaffoldapy` is untouched and still owes its half, including the e2e tier that
is the only thing testing what it generates.

That plan also carries the `node20-action-deprecation` `[DEFERRED:]` about this consumer's `ci`
namespace. **It is resolved** — see the last section.

## What the sweep did

`inv deps.lock --package repo-tasks` (`9d57d464` -> `7bb880b0`), `uv sync`, `configs.pull`,
`configs.ensure-deps`, `deps.lock`, `uv sync`, gate. Note the ordering correction worth folding into
`contributing/consumer-sweep.md`: **the pin bump comes first, before `configs.diff` is read at
all.** That doc's own pitfall says `configs.pull` reads the installed package, and in a consumer
that pins `repo-tasks` in its own lock the installed package is whatever the lock says — so a
`configs.diff` run before the bump reports drift against the old shipped configs and a `pull` then
writes them. Running `diff` first, as the sweep's command list has it, produced exactly that: an
identical report before and after the bump, which looks like the bump changed nothing.

`inv venv.sync` in that list also does not exist in this consumer — it publishes no `venv`
collection. Plain `uv sync` is what was run.

## Which way each prediction went

| item                                   | prediction                       | outcome                                           |
| -------------------------------------- | -------------------------------- | ------------------------------------------------- |
| `ae54087` `pytest-socket`/`pytest-cov` | `configs.diff` exits 1, CI green | **diff fired**; `pytest-timeout` was missing too  |
| `8f384d7` `pytest.ini` ResourceWarning | inert here                       | **inert** — 573 tests, no change in outcome       |
| `949607c` `ruff.toml` `target-version` | check `requires-python` exists   | **exists** (`>=3.11`), linter stays at 3.11       |
| `c514bd9` derived `pythonVersion`      | can turn a green consumer red    | **it did** — see below, the one real finding      |
| `c514bd9` derived `anyio_mode`         | emitted iff the lock has AnyIO   | **emitted**, correctly — AnyIO is in that lock    |
| packaged-`tests/` pair                 | inert, no ordering hazard        | **inert** — no `src/`, `tests/` left unpackaged   |
| `b79b76a` `--python-version`           | additive, nothing to check       | present, unused                                   |
| `de596ce` `venv.check`/`venv.recreate` | reports a mismatch everywhere    | **not run** — no `venv` collection published here |
| `3a58b1d` `docs.link-check` fix        | could turn red to green          | no change; that repo's docs were already green    |

Both halves of `configs.diff` fired on the same run for the first time, as
`2026-08-25-consumer-transitions.md` predicted they would: config-file drift on three files and
dev-group drift on two entries.

## The one real finding, and it is the predicted one

**`pythonVersion` derived into `pyrightconfig.json` moved the type checker from the developer's 3.14
venv to the declared 3.11 floor, and two test modules failed immediately** —
`from typing import
override`, which is 3.12+. They had been passing only because nothing was
checking at the floor. The repo had even declared `typing-extensions` as a dev dependency for
exactly this, with a comment saying so, and a third test module already used the right import; the
two others had simply drifted.

This is the finding rather than a regression, and it is the strongest evidence the sweep produced:
`c514bd9` is doing precisely what its design says, on the first consumer it reached.

**CI is green, so the prediction holds for this consumer.** Pushed 2026-09-05; run `33985012776` and
its siblings on `d193783` report `success` for `CI`, `Deploy docs to GitHub Pages` and
`Dependency Graph`. That is the half that could not be tested locally, and it went the way
`2026-08-25-consumer-transitions.md` said it would: `configs.diff` fired on both halves while
nothing in CI changed outcome, because none of the pending changes is a binary a gate step shells
out to.

[UNVERIFIED: the `[UNVERIFIED:]` in `2026-08-25-consumer-transitions.md` about `require_tool`'s
preflight never having fired from a consumer's own CI is **not** answered by this sweep, and could
not be — none of these changes is a gate binary, so nothing here could make it fire. It is still
waiting on the first family-wide manifest change that adds one.]

## The `node20` deferred is resolved for this consumer

`plans/2026-08-28-node20-action-deprecation.md`'s last `[DEFERRED:]` asked for two halves to land
together — a `repo_tasks` bump in that repo, then the `ci` collection — because the pinned package
predated `e51e062` (annotation printing) and `9f3a03f` (`check_actions`), so wiring it alone would
have published the exact blind spot the deprecation hid in.

Both halves are now in place, and the ancestry was checked rather than assumed: `e51e062` and
`9f3a03f` were both already ancestors of the **old** pin `9d57d464`, so the collection wired there
on 2026-09-04 was never publishing the blind-spot version. The bump was owed anyway; the ordering
hazard that plan describes turned out not to have existed.

Run from that repo, against the bumped pin:

```
inv ci.status --branch master --limit 3   # three green runs, no annotations printed
inv ci.check-actions                      # 0 of 5 action(s) behind
```

Silence from `ci.status` is the result that matters — the same command printed the Node 20 warning
under green runs before the bump there. `--branch master` is still needed on every call, since the
task's default is `main`; that is a per-consumer ergonomic rather than a defect, but it is worth
knowing that this consumer can never use the bare form.

## Recommended direction

1. **Correct `contributing/consumer-sweep.md`'s command order** — the pin bump for a lock-pinning
   consumer belongs above `configs.diff`, not in the pitfall below it, and `inv venv.sync` should
   say "or `uv sync` where the consumer publishes no `venv` collection".
2. **Record this half in `plans/2026-08-25-consumer-transitions.md`** and leave the batch open for
   `scaffoldapy`, whose e2e tier is the only thing that tests generated repos.
3. **Close the `node20` deferred**, noting the ancestry finding above so nobody re-derives it.

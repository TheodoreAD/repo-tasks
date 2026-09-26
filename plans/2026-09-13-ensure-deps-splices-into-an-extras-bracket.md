---
status: in-progress
updated: 2026-09-26
source_repo: github.com-personal/ingesta
source_session: 21c18768-649d-4753-9dca-e23e5b9555d3.jsonl
source_moment: 2026-09-13
source_plan: plans/2026-09-13-repo-tasks-consumer-sweep.md
---

# `configs.ensure-deps` splices into the first `]`, which can be inside an extras name

## Context

Found running the consumer sweep in `ingesta` on 2026-09-13, with the installed `repo-tasks` v0.3.0
tool. Nothing was written to `repo-tasks`; the consumer's `pyproject.toml` was restored and the two
entries added by hand.

That consumer's `dependency-groups.dev` starts with the project's own extras:

```toml
dev = [
  # The suite exercises the store and the bot, so the development environment installs the extras
  # the wheel does not carry, plus the SQLite driver the test tier runs against.
  "ingesta[store]",
  "ingesta[bot]",
  ...
]
```

`inv configs.diff` reported exactly two missing entries, `pytest-socket` and `pytest-timeout`, which
was correct. `inv configs.ensure-deps` then printed `added` for **all fourteen** manifest entries,
including the twelve already present, and wrote this:

```toml
dev = [
  # The suite exercises ...
  # the wheel does not carry, plus the SQLite driver the test tier runs against.
  "ingesta[store  "basedpyright>=1.39.10",
  "invoke-stubs @ git+https://github.com/TheodoreAD/invoke-stubs",
  ...
  "act-bin",
]",
  "ingesta[bot]",
```

The file no longer parses as TOML. The consumer's gate would have refused it at `uv lock --check`,
but only if it ran before a commit.

## Evidence

The cause, read from source at `src/repo_tasks/configs.py`:

- `_DEV_ARRAY_RE = re.compile(r"dev\s*=\s*\[(?P<items>.*?)\]", re.DOTALL)` (line 44) is non-greedy
  to the **first** `]`, which is the one inside `"ingesta[store]"`.
- `items` is therefore the two comment lines plus `"ingesta[store` with no closing quote, so
  `re.findall(r'"([^"]+)"', ...)` (line 627) finds no entries, every manifest entry counts as
  missing, and the insertion goes at the match's end, inside the string.
- `configs.diff` reads the same list with `tomllib` (line 281) and got it right. **Two readers of
  one list disagree**, which is how the diff and the splice reported different things in the same
  run.

Any consumer whose dev group names an extra (`"pkg[extra]"`, the ordinary way to pull a project's
own optional dependencies into development) before the end of the list is exposed. A `[` in a
comment inside the array would do the same.

**Who is exposed today, measured 2026-09-18** by running `_DEV_ARRAY_RE` against each declared
consumer's `pyproject.toml` and counting what the capture yields:

| consumer                 | entries captured | actual | exposed |
| ------------------------ | ---------------- | ------ | ------- |
| `power-user-linux-setup` | 16               | 16     | no      |
| `scaffoldapy`            | 15               | 15     | no      |
| `invoke-stubs`           | 14               | 14     | no      |
| `agent-skills`           | 12               | 12     | no      |
| `ingesta`                | **0**            | 14     | **yes** |

So this blocks nothing in the three sweeps still outstanding, and it is **not** historical:
`ingesta`'s file was restored and its two entries written by hand, which removed the damage and left
the exposure exactly where it was — `"ingesta[store]"` still opens the group, so the next
`configs.ensure-deps` run in that repo corrupts it again. The count of 0 is the signature to look
for; a consumer reporting every manifest entry missing when `configs.diff` reports two is this bug
and nothing else.

## Recommended direction

Decide the membership question with `tomllib`, which the diff already does, so the two commands
cannot disagree about what is present. The splice position still needs the text, since `tomllib`
does not round-trip; the closing bracket has to be found by a scan that skips quoted strings and
comments rather than by the first `]`. A regression test with an extras entry first in the list, and
one with a `[` in a comment, both asserting the result still parses and only the missing entries
were added.

## Landed 2026-09-26, `a0ee510`

Exactly as recommended, with two things the direction above did not anticipate.

**A second shape was wrong for the same reason, in this repo.** `_declared_dev_specs`' docstring had
already recorded it — a text reader sees `dev = [{ include-group = "repo-tasks-quality" }]` as
declaring nothing — but only as an argument for why `diff` uses tomllib, never as a live defect in
`ensure_deps`. It is one: run here before the fix, `ensure_deps` would have spliced the whole
manifest into the repo that authors it. The case was understood one layer down and unhandled one
layer up, which is the same sentence that plan wrote about the `invoke-stubs` self-reference three
weeks earlier.

**The scan is anchored to the `[dependency-groups]` table**, not to the first `dev = [` in the file
as the old regex was. Once membership and position come from different readers, splicing into a
different array than the one measured is a new way to be wrong — and `dev` is not a unique key in a
pyproject.toml, since pdm and poetry both spell dev groups under tables of their own.

`_scan_past_array` skips comments and all four TOML string forms, and tracks `[`/`]` depth so a
nested array cannot end the outer one.

## Verification

**Eight regression cases, six of which fail against the previous code** — extras entry first, extras
entry last, a bracket inside a comment, an inline table before the strings, a marker quoting inside
a basic string, this repo's own `include-group` shape, a `dev` array under
`[tool.pdm.dev-dependencies]` alongside the real one, and the byte-identical survival of the extras
entry itself. Proved by reverting only `configs.py` and re-running them, not by reasoning about the
diff. The two that pass either way are coverage rather than regression proof, and are labelled as
such here rather than counted.

**The original repro, replayed on that consumer's own file.** The attached `verify_repro.py` reads
`ingesta`'s real `pyproject.toml`, rewinds its dev group to the pre-repair state this plan records
(the two manifest entries absent, `"ingesta[store]"` still first), runs `ensure_deps` on a scratch
copy and asserts the outcome. Result: the file parses, `"ingesta[store]"` is still entry 0, exactly
`pytest-socket` and `pytest-timeout` were added, and every other byte is identical. The run prints
`already present` for the other twelve, which is the precise inversion of the 2026-09-13 symptom —
`added` for all fourteen. Nothing in that repo was written; the script re-reads the source file
afterwards and asserts it unchanged.

~~[DEFERRED:~~ **Done 2026-09-26, and smaller than this entry expected:** one guard,
`configs.unreadable_pyproject`, checked at the top of `ensure_deps` and `diff` before anything
parses, so nothing in the task's opening had to move. `consumers.diff` reports it as that consumer's
line and keeps measuring the rest, where a traceback used to end the loop. Three tests, all failing
with the raw traceback against the previous code. The original entry follows. **A consumer whose
`pyproject.toml` is already corrupt gets a `TOMLDecodeError` traceback rather than a sentence.**
Deliberately not fixed here, and recorded because it was noticed and skipped rather than missed. Now
that membership comes from tomllib, `ensure_deps` cannot run at all against an unparseable file —
which is the state this bug used to _create_, so its own victims are the people who would meet it.
The failure is safe: it raises from `_applicable_quality_deps` before anything is written. Making it
a clean `Exit` naming the likely cause means restructuring the task's opening, since `canonical` is
computed above the `pyproject_path.exists()` check, and that is a bigger edit than the message is
worth on its own. Worth doing next time that function is touched for another reason.]

[UNVERIFIED: **the fix has not been run inside `ingesta` itself**, which is what this plan's
`source_repo` owes — the replay above uses that consumer's real input but this repo's working-tree
code, not the global tool in that tree. Discharging it needs `inv repo-tasks.update` there once this
is pushed and released, and then `configs.ensure-deps` in that repo's own session. It is the sweep
step rather than a separate errand, and `ingesta`'s dev group is currently complete, so the honest
repro there is the rewind the script does. Until then, **any consumer still on a `repo-tasks` older
than this keeps the bug**, which is recorded in `contributing/consumer-sweep.md` as a live pitfall
rather than a historical one.]

## Attachments

- `verify_repro.py` — committed, 2 KB, attached 2026-09-26

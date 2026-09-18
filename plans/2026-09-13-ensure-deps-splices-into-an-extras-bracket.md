---
status: idea
updated: 2026-09-13
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

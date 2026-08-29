---
status: landed
updated: 2026-08-29
repo: git@github.com:TheodoreAD/repo-tasks.git
---

# `docs.link-check` reads inline code as a markdown link

## Context

Hit 2026-08-29 in a consumer repo, writing documentation about PEP 695 generics. The gate failed
with four broken links, none of which were links:

```
[docs.link-check] contributing/modelling.md:106: ...
[docs.link-check] AGENTS.md:121: ...
```

The reported target really is the three-character string `...`. The source text was inline code:

    `def evolve[T: BaseModel](...)`

`[T: BaseModel](...)` is a syntactically valid markdown inline link whose target is `...`, so
`_LINK_RE` matches it, `_bad_link` resolves `...` against the file's directory, finds nothing, and
reports it broken.

`_relative_links` in `src/repo_tasks/docs.py` skips **fenced** blocks — deliberately, with a comment
saying a code sample showing markdown syntax is documentation rather than a link. It does not skip
**inline code spans**, and the same reasoning applies to them exactly.

## Why it matters more than it looks

The false positive is not exotic. Any prose about a generic subscript immediately followed by a call
or parameter list produces it, and that is ordinary Python:

- `def f[T](x: T) -> T` — PEP 695, which every repo will be writing about as floors move to 3.12+
- `Annotated[int, Field()]` is safe, but `list[str](...)`, `dict[str, int](...)`, `cast[T](...)` are
  not
- `data["key"](arg)` — a dict of callables

The failure mode is the wrong one for a gate: it is **red on correct input**, and the only way to
get green is to reword prose around a bug. In the repo that hit it, three files had to drop `(...)`
from otherwise natural sentences. That teaches every future writer a superstition instead of a rule.

## Recommended direction

Strip inline code spans before matching, the same way fenced blocks are already skipped. Roughly:
remove `` `...` `` (and `...` for spans containing backticks) from each line before running
`_LINK_RE` over it, replacing with a placeholder of the same length so reported column positions do
not shift.

The docstring's stated philosophy is already the right one and should be extended rather than
revisited: "no reference-style definitions, no HTML anchors, no bare autolinks — every one of those
is a way to write a link this does not check, which is a smaller failure than flagging text that is
not one." A link inside a code span is exactly that trade, and currently falls the wrong side of it.

Both open questions are now answered.

**A real link inside an inline code span: none exists.** Every markdown file under the personal
projects root was parsed twice, once with spans blanked and once without, and the difference was
compared. The only targets that disappear are the five false positives in this plan's own text; no
resolving link in any repo is lost. A crude `rg` for the shape returns dozens of apparent hits, all
of which are a span _closing_, a real link, and the next span _opening_ — the pattern spans two code
spans rather than sitting inside one, which is why the measurement had to parse rather than grep.

**The indented-code-block form has the same hole, and is deliberately left open.**
Four-leading-space blocks are not recognised by `_FENCE_RE`, so a raw markdown link in one is still
reported. Widening the fence rule to a bare indent test would silently stop checking real links in
nested list items, which is the worse failure — see `2026-08-29-link-check-indented-code-blocks.md`.

## Verification

`test_relative_links_skips_inline_code_spans`, plus a multi-backtick span case and one asserting a
real link whose _text_ contains code still resolves. `inv quality.precommit` green on the commit
that introduced them, with this plan file — the thing that was red — in the tree.

## Migrated to

- **The fix and its reasoning** — `src/repo_tasks/docs.py`: `_CODE_SPAN_RE`'s comment carries the
  PEP 695 example, and `_relative_links`' docstring carries the `[PITFALL:]` about the gate going
  red on correct input and the family-wide measurement that says stripping spans loses nothing. That
  module's docstrings are where this repo keeps `link_check`'s rationale; there is no separate
  `contributing/` page for it and one file would not have earned its place.
- **The exact shapes that broke** — `tests/unit/test_docs.py`, three regression tests.
- **The indented-code-block residue** — `plans/2026-08-29-link-check-indented-code-blocks.md`,
  including the list-continuation pitfall that is the reason it was not fixed here, and the open
  `markdown-it-py` question that would subsume it.

Not migrated: the "Why it matters more than it looks" catalogue of shapes (`list[str](...)`,
`dict[str, int](...)`, `data["key"](arg)`). One example in the code comment carries the point, and a
list of variations on it is padding in a docstring. It stays readable here in git history.

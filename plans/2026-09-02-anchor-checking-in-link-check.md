---
status: landed
updated: 2026-09-04
source_repo: /home/tdumitrescu/projects/github.com-personal/power-user-linux-setup
source_session: # transcript filename, or blank
source_moment: # ISO timestamp of the turn
---

## Context

`docs.link_check` verifies that a relative markdown link names a file that exists. It deliberately
stops there — `src/repo_tasks/docs.py:59-64`:

> The fragment is stripped and not checked further — `file.md#heading` verifies the file, never the
> heading, so a renamed heading still passes. Whole-document fragments (`#heading` alone) are
> filtered out before this.

So the one link class the gate does not cover is the one a rename actually breaks. In
`power-user-linux-setup` that is not hypothetical: renaming a heading in `docs/ssh.md` passed
`inv quality.precommit` twice and broke the GitHub Pages deploy both times, on an anchor cited from
`docs/claude-code.md` (recorded 2026-08-28 in that repo's
`plans/2026-08-27-docs-site-usability.md`). The rename also skipped `plan-docs`' own "grep inbound
references before renaming a section title" step — which is the point: that discipline is written
down, was still missed, and nothing mechanical caught it.

`link_check` is the right home rather than a docs-site build. It needs no zensical and no dependency
at all, which is why it already runs in `check`; anchor resolution needs nothing more. The
alternative — putting `zensical build --strict` in the gate — is slower, and covers only the one
repo in the family that publishes a site.

**That alternative landed anyway on 2026-09-04**, for its own reasons, from
`2026-09-04-docs-build-in-the-quality-gate.md` (now retired). It does not make this redundant, and
the reason is the sentence above: the strict build sees only a repo that _has_ a docs site and only
the pages inside it, while this sees every tracked markdown file. `repo-tasks` has no site at all
and 9 fragment links; `power-user-linux-setup`'s `plans/` and `contributing/` are outside its
`docs/` tree. Neither subsumes the other in the other direction either — a strict build catches an
unresolved nav entry, which no anchor checker would.

## Evidence

Measured 2026-09-02 with a throwaway implementation of the design below, over `git ls-files '*.md'`
in each repo:

| repo                     | fragment links | same-file | cross-file | unresolved |
| ------------------------ | -------------- | --------- | ---------- | ---------- |
| `power-user-linux-setup` | 79             | 59        | 20         | 0          |
| `agent-skills`           | 29             | 29        | 0          | 0          |
| `repo-tasks`             | 9              | 0         | 9          | 0          |
| `scaffoldapy`            | 0              | 0         | 0          | 0          |
| `olx-polite-mcp`         | 0              | 0         | 0          | 0          |

**Nothing in the family needs cleaning up first**, so this can land straight into `check` rather
than behind a flag or a grace period.

The measurement was also shown to fail: a two-file fixture where `a.md` links `b.md#the-old-heading`
and `b.md` carries `## The new heading` reports exactly that one link, while a valid same-file
`#page-a` in the same document passes. A check that has only ever printed zero is not evidence of
anything.

[PITFALL: the first run reported 2 unresolved links, and **both were the checker's bugs, not the
repos'** — the shape to expect from this feature. (1) Treating `_` as emphasis when flattening a
heading turns `## Whole-file configs — config_files` into `configfiles`, an anchor no slugger would
ever emit; underscores are identifiers in these docs, not markup. (2) GitHub does **not** collapse
runs of spaces: `## Bash & the CLI allowlist (cluster intro)` loses the ampersand and keeps both
surrounding spaces, so the anchor is `bash--the-cli-allowlist-cluster-intro`, with a double hyphen.
A naive `\s+ -> -` gets it wrong. Both false positives were on links that resolve correctly in the
published site and on github.com.]

## Design

Extend `_bad_link` (or a sibling) to resolve the fragment when the target is markdown inside the
repo, and re-admit the whole-document `#heading` form that `_relative_links` currently filters out —
59 of the 79 fragment links in `power-user-linux-setup` are same-file, so dropping them would miss
most of the surface.

An anchor set per target file, built from:

- headings, slugified two ways (below), with duplicates suffixed the way each renderer does it —
  python-markdown appends `_1`, GitHub appends `-1`;
- explicit `attr_list` ids (`## Heading {#custom-id}`);
- inline `<a id="…">` / `<a name="…">`.

Reuse `_relative_links`' existing fence and code-span skipping for headings too — a `##` inside a
fenced block is a code sample, not a heading.

**Two sluggers, and a link passes if either matches.** The same markdown has two renderers in this
family: `power-user-linux-setup`'s `docs/` is published by zensical through stock
`markdown.extensions.toc` (verified in its `mkdocs.yml` — `permalink: true`, no custom `slugify`),
while `plans/`, `contributing/`, `AGENTS.md` and every README are read on github.com. The algorithms
agree on the common case and differ on punctuation and space runs, so requiring one would fail
correct links in the other renderer.

```python
def _toc_slug(text: str) -> str:  # markdown.extensions.toc.slugify
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def _gh_slug(text: str) -> str:
    value = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return value.replace(" ", "-")  # each space its own hyphen; runs are NOT collapsed
```

Heading text is flattened first — link syntax reduced to its text, backticks removed, `*` emphasis
removed, `_` left alone (see the PITFALL above).

## Open questions

~~Is the union too lenient?~~ **Left as the union, 2026-09-04**, per direction 3 below. A link that
resolves on github.com but not on the published site would pass, and the sharper rule is available —
when a repo has a site config, check files under its docs directory against the toc slugger alone
and everything else against the union. It costs a config read and a directory rule, only one repo in
the family would exercise it, and no such link has been found. Revisit when one is.

~~How much markdown flattening is enough?~~ **The cheap insurance was taken instead of an answer**,
2026-09-04. Links, code spans and `*` emphasis cover every real link in the family; footnote
markers, HTML inside headings and emoji shortcodes are still unhandled and still absent. Rather than
guess at the next one, an unresolved fragment now reports the closest surviving anchor, so a future
false positive is diagnosable from the failure message rather than from this file.

~~Does `power-user-linux-setup` still want `zensical build --strict` in its gate?~~ **Moot, answered
by events on 2026-09-04**: the strict build is now a step in the shared `quality.check` for every
consumer that has an `mkdocs.yml`, so that repo gets it by pulling the update rather than by
choosing. The two checks were landed for different failures and overlap only partially — see the
Context section. Nothing here is waiting on that repo.

## Recommended direction

1. Land the anchor resolution in `link_check` with the two sluggers, the fixture above as a test,
   and both false-positive shapes as regression tests (`config_files`, `Bash & the …`).
2. Re-run across the family before release — the table above is the baseline; anything non-zero
   afterwards is either a real dangling anchor or a slugger bug, and the two are told apart by
   opening the link.
3. Leave the site-strictness question until a real link is found that works on GitHub and not on the
   site.

## Landed, 2026-09-04

All three steps, as written. The design needed no revision — the two sluggers, the flattening rules
and the union were taken from this plan verbatim, and the throwaway implementation it was measured
with turned out to be the right shape.

Both remaining open questions were answered by doing it rather than by deciding:

- **Is the union too lenient?** Left as the union, per direction 3. No link was found that resolves
  on github.com and not on the site, so the sharper rule has no case to answer yet and would cost a
  config read and a directory rule to serve one repo.
- **How much flattening is enough?** The plan's own cheap insurance was taken: an unresolved
  fragment reports the **closest surviving anchor** via `difflib`. A rename is usually a near miss,
  so that turns the report into the fix — and when the miss is a slugger bug instead, the computed
  neighbourhood is right there in the failure rather than in this file.

[PITFALL: **a third slugger bug, and the tests found it rather than the family sweep.** One
duplicate counter shared between the two sluggers counts every heading twice, so a second `## Notes`
comes out as `notes_2`/`notes-3` — anchors no renderer emits, on the exact shape duplicate suffixing
exists for. The family sweep could not have caught it: no repo here has a duplicate heading that is
also linked. So the measurement-over-the-corpus habit that found the first two bugs is not
sufficient on its own, and the fixture-shaped test is what covers the case the corpus lacks.]

Verified three ways rather than by a clean run:

- **The plan's own fixture**, as an end-to-end test through `link_check.body` — `a.md` cites
  `b.md#the-old-heading`, `b.md` carries `## The new heading`, the task exits non-zero naming the
  anchor. Only `git ls-files` is mocked.
- **Both false-positive shapes** as regression tests, plus the duplicate-suffix, attr_list,
  HTML-anchor, fenced-heading and same-file cases. 572 tests green.
- **The family sweep re-run read-only**, and its counts line up with this plan's independently
  measured table: `repo-tasks` 9 fragment links, `agent-skills` 29, `scaffoldapy` 0,
  `power-user-linux-setup` 85 (79 when measured on 2026-09-02, grown since). **0 unresolved
  everywhere**, so nothing in the family needs cleaning up and this could land straight into
  `check`, exactly as the evidence section predicted. Two independent implementations agreeing on
  the counts is the part worth noting — it is evidence about the sluggers, not just about the repos.

What is **not** verified here: the original `docs/ssh.md` repro, in the repo where it happened. This
plan carries `source_repo`, and a fix checked only where it was written has not met the case that
produced it. Filed as `power-user-linux-setup`'s `2026-09-04-docs-build-gate-verification.md`, which
covers both new checks in one pass since both land there together.

## Migrated to

- [`../contributing/quality-gate.md`](../contributing/quality-gate.md), "In the gate" — the union
  decision, why this belongs in `link_check` rather than being left to the strict docs build, and
  the three slugger bugs. Landing this also made two claims in that file's own `docs.build` entry
  false, written hours earlier: that the strict build was the only thing in the family that could
  see a dangling anchor, and that `link_check` exits 0 on that input. Both corrected, with the
  anchor claim kept as dated history rather than a standing fact.
- `src/repo_tasks/docs.py` — the two sluggers, the flattening rule and the fence skip carry their
  own pitfall comments, since each exists because of a specific false positive and the code alone
  reads like arbitrary regex choices.

**Deliberately not migrated.** The per-repo measurement table stays here and dies with the plan: it
was a baseline for deciding whether this could land without a cleanup pass, that question is
answered, and a table of link counts is stale the day after it is written. The sweep script that
produced it is a scratchpad throwaway, not a task — the standing version of that measurement is the
gate step itself, now running on every commit in every consumer.

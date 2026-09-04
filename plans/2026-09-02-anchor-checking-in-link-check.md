---
status: idea
updated: 2026-09-02
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

[NEEDS CLARIFICATION: is the union too lenient? A link that resolves on github.com but not on the
published site would pass, which is precisely the `docs/ssh.md` failure class this exists to catch.
A sharper rule: when the repo has a site config (`mkdocs.yml`/zensical present), files under its
docs directory are checked against the toc slugger alone, everything else against the union. That
costs a config read and a directory rule, and only one repo in the family would exercise it — worth
it or not is the open part.]

[NEEDS CLARIFICATION: how much markdown flattening is enough? The measurement handled links, code
spans and `*` emphasis and that was sufficient for 117 real links across the family. Footnote
markers, HTML inside headings, and emoji shortcodes are all unhandled and none appear today. The
cheap insurance against a future one is to report an unresolved fragment together with the candidate
slugs it computed, so a false positive is diagnosable from the failure message rather than by
reading this plan.]

[NEEDS CLARIFICATION: `power-user-linux-setup`'s gate still does not run `zensical build --strict`
(its own plan records the reasoning as an open choice). Anchor checking removes the specific failure
that motivated it, but not every strict-build failure — an unresolved nav entry, say. Whether that
repo still wants the build in its gate afterwards is its call, not this one's.]

## Recommended direction

1. Land the anchor resolution in `link_check` with the two sluggers, the fixture above as a test,
   and both false-positive shapes as regression tests (`config_files`, `Bash & the …`).
2. Re-run across the family before release — the table above is the baseline; anything non-zero
   afterwards is either a real dangling anchor or a slugger bug, and the two are told apart by
   opening the link.
3. Leave the site-strictness question until a real link is found that works on GitHub and not on the
   site.

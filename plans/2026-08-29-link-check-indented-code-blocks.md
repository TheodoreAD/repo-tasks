---
status: idea
updated: 2026-09-08
---

# `docs.link-check` does not recognise indented code blocks

## Context

The residue of the inline-code-span fix (commit `3a58b1d`, retired plan
`2026-08-29-link-check-reads-inline-code-as-a-link.md`). `_relative_links` skips fenced blocks and,
since that commit, inline code spans. It still does not recognise markdown's other code block form,
four leading spaces:

```markdown
see [example](does/not/exist.md)
```

That line is a code sample and gets reported as a broken link. It has to be shown wrapped in a fence
here, because writing it plainly makes this plan fail the gate it describes — which is the whole
bug, demonstrated on the first draft of this file. In practice the hole is narrow — the span fix
already covers anything inside backticks, and an indented sample containing a raw markdown link is
rarer than one containing a generic subscript — but it is the same class of failure: red on correct
input.

## Why it was not fixed with the spans

Widening `_FENCE_RE` to "four leading spaces" is wrong, and the reason is worth keeping:

[PITFALL: a list item's continuation lines are indented too — commonly four spaces under a `-`
marker — and this family's docs are full of nested bullets carrying real relative links. A naive
indent rule would silently stop checking those, turning a false positive into a false negative on
exactly the links most likely to break during a plan retirement, which is the failure this task
exists to catch.]

CommonMark's actual rule distinguishes them: an indented chunk cannot interrupt a paragraph, and
inside a list item the indent is measured relative to the item's content column, not the line start.
Implementing that is a real block-structure pass, not a regex.

## Open questions

[NEEDS CLARIFICATION: is it worth fixing at all? The docstring's stated trade — missing a link is a
smaller failure than flagging text that is not one — argues yes. Against: a correct implementation
needs list-aware indent tracking, which is a large step up in complexity for a shape that has
produced zero real hits in this family so far. "Reword the sample as a fenced block" is a cheap
workaround with no superstition attached, unlike the inline-span case, where the workaround was
mangling prose.]

[NEEDS CLARIFICATION: would pulling in a real markdown parser be better than growing this one?
`markdown-it-py` would give correct block structure and inline-code handling for free, and would
also close the reference-style-definition and autolink gaps the docstring lists as deliberate.
Against: `link_check` is currently the one docs task that needs no dependency at all and so runs in
the gate — see the module docstring. That property is the reason it exists in the gate, and trading
it away needs a deliberate decision, not a drive-by.]

## The other scope the task deliberately does not cover

**The anchor half is done, and this entry used to claim both halves were open.** `7fc0b23` added
`_anchors`, which resolves a link's fragment against the union of what python-markdown's toc
extension and github.com would emit, per tracked `.md` and cached per run — so a renamed heading is
now caught, and the report names the nearest surviving anchor. It needed no parser and no
dependency, which is the part worth keeping: the entry below predicted the opposite.

[DEFERRED: **external URLs**, and only those. `docs.link-check` checks relative file links and their
fragments; a scheme-bearing target is skipped by `_EXTERNAL`, because checking one is a network call
and that is what keeps the task in the gate
([`../contributing/quality-gate.md`](../contributing/quality-gate.md)). Moved here from the retired
quality-gate sweep plan, because it is the same task's scope question. `lychee-bin` remains the tool
if this is ever wanted, at 78 MB and one release ever; its maintenance record is worth re-checking
before adopting rather than trusting the 2026-08 measurement.]

[PITFALL: this entry said "a real parser closes the anchor half locally", pairing that half with the
`markdown-it-py` question above and making both look like one decision. They were not: anchors are a
heading-slug problem, not a block-structure one, and `7fc0b23` (2026-09-04) closed them with two
sluggers and a regex while leaving `markdown-it-py` exactly as open as before. A scope note that
bundles a gap with a proposed mechanism makes the gap look more expensive than it is — and it
outlives the fix, since nothing sends the session that closes the gap back to the plan that
mispriced it: this entry still claimed the anchor half was open four days after it shipped.]

## Recommended direction

Leave it open. Revisit when an indented sample actually trips the gate, or when the `markdown-it-py`
question is answered for its own reasons — that answer subsumes this one.

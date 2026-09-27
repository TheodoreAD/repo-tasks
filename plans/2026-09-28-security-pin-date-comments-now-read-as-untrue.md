---
status: idea
updated: 2026-09-28
source_repo: github.com-personal/invoke-stubs
source_session: 76d98521-8e7c-4524-bb4f-4caeb36e8cb0.jsonl
source_moment: 2026-09-28
source_plan:
---

# Every consumer's `security-reusable.yml` pin now fails the pin-comment check

**This reports a fact**, so `source_plan` is blank. The decision about what to do with it belongs to
this repo, in `plans/2026-09-10-action-pinning-and-currency.md`.

## Context

`ci.check-actions` gained the pin-comment check 2026-09-26, and it was verified live against this
repo's own `publish.yml` pins. The consumer side was not checked. Every consumer pins the shared
audit as:

```yaml
uses: TheodoreAD/repo-tasks/.github/workflows/security-reusable.yml@d17c60715e2a7fd63cf22874255c6923277b7859 # 2026-08-31
```

The date comment was written before this repo had tags, and the check now reports it with v0.5.0:

```
[ci.check-actions] TheodoreAD/repo-tasks@d17c60715e2a  UNTRUE COMMENT — says 2026-08-31, but 2026-08-31 is not a tag of TheodoreAD/repo-tasks
```

## Evidence

Found adding CI to invoke-stubs 2026-09-28, which started from the scaffoldapy template's
`security.yml`. That exact line is in four files:
`scaffoldapy/template/.github/workflows/security.yml` (so every newly generated project gets it),
and the `security.yml` of `scaffoldapy`, `ingesta` and `power-user-linux-setup`.

`security-reusable.yml` is byte-identical between `d17c607` and `v0.5.0`
(`git diff --stat d17c607 v0.5.0 -- .github/workflows/security-reusable.yml` is empty). So
re-pinning to the v0.5.0 commit (`9398008fa87d0215d0a7167226bfcb7d44ae4a82`) with `# v0.5.0` is the
same audit with a checkable comment. invoke-stubs did exactly that (`763c099`), and
`ci.check-actions` then reported it current with no untrue line.

## Recommended direction

Re-pin the template first, since it is the copy that multiplies, then the three consumers at their
next sweep. Two consequences follow. Once pins name tags, `ci.check-actions` can report them as
behind, which the date comment never allowed. And the comment in each caller that says "repo-tasks
publishes no releases, so the date is what there is to name" is no longer true, so it should go in
the same change.

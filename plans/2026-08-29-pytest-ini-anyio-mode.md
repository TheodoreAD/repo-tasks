---
status: idea
updated: 2026-08-29
repo: git@github.com:TheodoreAD/repo-tasks.git
---

# A consumer's `pytest.ini` needs a line the canonical one does not have

## Context

`pytest.ini` is one of the files `configs.pull` materialises, and the file says so in its own
header: it ships to every consumer, and a change worth making is almost certainly worth making
family-wide. That works while every consumer wants the same file.

One consumer now does not. A repo whose test suite is partly async needs

```ini
anyio_mode = auto
```

in `pytest.ini` — AnyIO's plugin reads it from the ini file and there is nowhere else to put it,
because pytest reads exactly one config file and `pytest.ini` wins over `pyproject.toml` whenever it
exists. The line was added locally on 2026-08-29. `configs.pull` would silently take it back out,
and the failure that follows is loud but misleading: every async test raises rather than running,
with a warning about an un-awaited coroutine rather than a message about configuration.

So the local edit is a divergence with a countdown on it, and this is the general question rather
than that one repo's problem: **what happens when a consumer legitimately needs a line the canonical
file does not have?**

## Open questions

[NEEDS CLARIFICATION: Whether `anyio_mode = auto` belongs in the canonical file for everyone. It is
inert in a repo with no async tests and no AnyIO installed — the plugin is not loaded, so the ini
key is simply unread, though `--strict-config` may object to an unknown key, which is exactly the
thing to measure before assuming. If it is inert, this is one line in one file and the general
question below can wait for a second, less lucky case.]

[NEEDS CLARIFICATION: Whether pulled configs should support a per-repo append at all — a
`pytest.local.ini` merged in, a marked block the pull preserves, or a documented "these keys are
yours" region. Every mechanism here has a cost: a pull that preserves anything stops being a
byte-for-byte materialisation, and "why does this repo's config differ" becomes a question with two
possible answers instead of one.]

[NEEDS CLARIFICATION: Whether `configs.diff` should report a local edit to a pulled file loudly
enough to be noticed. It compares against the canonical copy already; what is missing is anything in
the routine `quality.precommit` path that surfaces the difference, so a diverged file stays diverged
silently until someone runs the pull that reverts it.]

## Recommended direction

Measure the inert claim first, because it decides how much of the rest matters. Add
`anyio_mode = auto` to the canonical `pytest.ini`, run a consumer repo with no AnyIO installed and
no async tests under `--strict-config`, and see whether pytest objects. If it does not, ship the
line and leave the general mechanism unbuilt until a second case turns up — one that is genuinely
per-repo rather than merely not-yet-shared.

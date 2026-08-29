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

**Answered 2026-08-29: it is not inert, and the answer is a hard failure.** With the shipped
`pytest.ini` plus `anyio_mode = auto`, in an environment holding pytest 9.1.1 and no AnyIO:

```
ERROR: Unknown config option: anyio_mode
...
collected 1 item
============================ no tests ran in 0.00s =============================
```

Exit code 4, no test executed — because `--strict-config` is already in the file's own `addopts`,
which is what turns the unread key into a fatal error rather than a warning. The same project with
AnyIO 4.14.2 added and nothing else changed collects and passes. So shipping the line family-wide
breaks every consumer that does not depend on AnyIO, which is most of them.

[PITFALL: this is only measurable in a genuinely isolated environment. The first run —
`uv run --no-project --with pytest` from a shell with this repo's venv active — reported
`plugins: anyio-4.14.2, socket-0.8.1, cov-7.1.0` and passed cleanly: the active `VIRTUAL_ENV` leaked
its site-packages in, so the probe measured a machine that had AnyIO all along and produced exactly
the "it is inert" answer being tested for.
`env -u VIRTUAL_ENV -u PYTHONPATH uv run --no-project
--python 3.11 --with pytest==9.1.1` is what
actually isolates it. Any future probe of "is this dependency absent" has the same hole.]

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

~~Measure the inert claim first~~ — done, and it went the unlucky way. The cheap escape is gone: the
line cannot ship family-wide, so the general question is live now rather than waiting for a second
case.

What that leaves, in rough order of cost:

1. **Ship AnyIO as a `repo-tasks-quality` dependency, then ship the line.** Restores the
   byte-identical file at the price of putting an async framework into every consumer's dev
   environment for a key most of them will never use. Cheapest mechanically, worst on principle.
2. **Build a per-repo append** — the second open question above. Now the leading candidate rather
   than a hypothetical, and its cost is the same one route B in
   `2026-08-29-python-floor-in-the-shipped-configs.md` pays: a pull that preserves anything stops
   being a byte-for-byte materialisation, and `configs.diff` needs the same rule or it reports drift
   forever. **The two should be decided together** — one mechanism serving both, or neither.
3. **Leave the consumer diverged and make the divergence loud** — the third open question above.
   Does not solve anything, but stops the silent revert, and is the only option that costs nothing
   until a decision is made.

Whichever wins, the affected consumer keeps a local edit until then, so option 3's noticing is worth
having regardless.

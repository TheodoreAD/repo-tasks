---
status: idea
updated: 2026-09-02
source_repo: github.com-personal/agent-skills
source_session: 2312636b-3f89-4cb5-95e8-48f986fb9ecb.jsonl
source_moment: 2026-09-01T17:20:53.485Z
---

# `docker login` and `helm registry login` hang on Python 3.14, and `pty=True` is why they look safe

## Context

An invoke task cannot run anything that waits for typed input — not through `c.run`, with or without
`pty=True`. Two independent causes, written up in full in `agent-skills`'
`skills/invoke-task-conventions/SKILL.md` under "A task may not run anything that waits for typed
input":

1. invoke echoes stdin itself on a non-pty run while the child reads `/dev/tty`, so the two race and
   the typed text is printed while the child re-prompts;
2. **on Python 3.14 invoke's stdin thread dies on the first keystroke** —
   `terminals.bytes_to_read()` passes a 2-byte buffer to `fcntl.ioctl(..., FIONREAD, ...)` for a
   4-byte result, which 3.14 hardened into `SystemError: buffer overflow`. Nothing is forwarded to
   the child, pty or not, and it waits forever. Upstream pyinvoke/invoke#1070, unreleased as of
   invoke 3.0.3.

`pty=True` appears to fix (1) and does nothing for (2), which is what makes it read as the correct
pattern right until the interpreter moves under it.

## The two call sites in this repo

Found by reading, 2026-09-02, from a session working in `agent-skills` — not touched here, because
writing into another repo's tree is not this session's to do:

| file                       | line | call                                                     |
| -------------------------- | ---: | -------------------------------------------------------- |
| `src/repo_tasks/docker.py` |  156 | `c.run(f"docker login {…}", echo=True, pty=True)`        |
| `src/repo_tasks/helm.py`   |  139 | `c.run(f"helm registry login {…}", echo=True, pty=True)` |

Both are credential prompts, which is the worst place for a silent hang. Their unit tests assert the
call shape verbatim (`tests/unit/test_docker.py:165`, `tests/unit/test_helm.py:107` and `:113`), so
the tests pass whatever the runtime does — they assert what is passed to a mock, never that a login
completes.

**Why this matters here specifically:** `repo-tasks` is installed as a uv tool, and
`power-user-linux-setup` pins `uv_python_default = "3.14"`. So the interpreter that hits cause 2 is
the family default, and every consumer inherits these two tasks.

## Open questions

[NEEDS CLARIFICATION: whether either login is reachable in practice, or whether both are always
preceded by a non-interactive credential source. `docker login` and `helm registry login` both take
`--password-stdin`, and CI almost certainly uses a token — so the hang may only bite an interactive
first run on a developer machine. That is still the case worth fixing, but it changes the urgency
and it decides whether this is a bug or a papercut.]

[NEEDS CLARIFICATION: whether the fix is `--password-stdin` with a token resolved from the
environment or a keyring, or the `run_interactive()` shape — a plain `subprocess` inheriting the
real terminal. The first removes the interactivity rather than accommodating it, which is the better
answer where a token exists; the second is the general escape hatch. `power-user-linux-setup` has a
worked implementation of the second in `util.run_interactive()`, with the reasoning in its
`contributing/interactive-input.md`.]

[NEEDS CLARIFICATION: whether the two unit tests should change. They assert the current call shape,
so they will fail on any fix and that is correct — but they are also the reason nothing caught this,
since asserting a mock's arguments cannot see a runtime hang. Worth deciding whether a test that can
observe the failure is available at all here, or whether this is a case where the container-level
reproduction in `power-user-linux-setup`'s `tests/containers/` is the only real oracle.]

## Recommended direction

Confirm reachability first — it is one read of each call site's surroundings and it decides
everything else. If a token is already available at both, `--password-stdin` is the smaller and
better change and the interactivity disappears rather than being handled.

## Evidence

- The interpreter matrix and both causes were reproduced in a container against invoke 3.0.3 across
  Python 3.10–3.14; the write-up lives in `agent-skills`' `skills/invoke-task-conventions/SKILL.md`,
  added 2026-09-02.
- The two call sites above were found with `rg 'pty=True'` over this repo, run read-only from the
  `agent-skills` session named in the frontmatter. The distinctive phrase to search that transcript
  for is the user asking to "continue witht he ones you can do".
- The originating incident was a first `inv wsl.install` on a corporate WSL machine, which hung
  after the sudo prompt with the password echoed in plain text.

---
status: landed
updated: 2026-09-05
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

[DECISION: both logins are reachable and interactive by design. Neither is called from CI
(`contributing/release-workflows.md`: CI authenticates through `docker/login-action` and never runs
`docker.login`), and both docstrings refuse to read, store, forward or echo a credential — the tool
prompts, the tool stores. So this is a bug, not a papercut: the two tasks exist only for the case
that hung. Settled 2026-09-05 by reading both call sites.]

[DECISION: `run_interactive` — a plain `subprocess.run` inheriting stdin/stdout/stderr — in a new
`interactive.py`, used by both logins. `--password-stdin` was rejected because it makes this package
handle the credential, the opposite of both tasks' stated stance, and no token source exists at
either site to feed it. Settled 2026-09-05.]

[DECISION: the unit tests change to assert the `run_interactive` call and that `c.run` is never
reached, with the same blind spot named in the test module's docstring: a mock's call shape cannot
see a runtime hang, and the oracle for a login completing is a real terminal, which only
`power-user-linux-setup`'s container tier has. Recorded as a pitfall in
`contributing/task-module-conventions.md` rather than left as an open question. Settled 2026-09-05.]

## Recommended direction

Confirm reachability first — it is one read of each call site's surroundings and it decides
everything else. If a token is already available at both, `--password-stdin` is the smaller and
better change and the interactivity disappears rather than being handled.

## Migrated to

Landed 2026-09-05.

- Both causes, why `pty=True` looked right, and why a subprocess with inherited stdio is the fix:
  `src/repo_tasks/interactive.py`'s module docstring, which both `docker.login` and `helm.login`
  point at.
- The rule, the pitfall that the tests passed throughout, and the rejected `--password-stdin`
  alternative: `contributing/task-module-conventions.md`, "A task may not run anything that waits
  for typed input through `c.run`".
- The interpreter matrix and the reproduction stay where they were written, in `agent-skills`'
  `invoke-task-conventions` skill; this repo cites it rather than copying it.

Not migrated: the call-site table, which is now wrong by design, and the originating
`inv
wsl.install` incident, which belongs to `power-user-linux-setup`.

## Evidence

- The interpreter matrix and both causes were reproduced in a container against invoke 3.0.3 across
  Python 3.10–3.14; the write-up lives in `agent-skills`' `skills/invoke-task-conventions/SKILL.md`,
  added 2026-09-02.
- The two call sites above were found with `rg 'pty=True'` over this repo, run read-only from the
  `agent-skills` session named in the frontmatter. The distinctive phrase to search that transcript
  for is the user asking to "continue witht he ones you can do".
- The originating incident was a first `inv wsl.install` on a corporate WSL machine, which hung
  after the sudo prompt with the password echoed in plain text.

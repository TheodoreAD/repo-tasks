"""Running a command that waits for typed input — a credential prompt, anything reading `/dev/tty`.

Never `c.run(..., pty=True)` for these, and not a plain `c.run` either. Two independent causes,
both reproduced in a container across Python 3.10 to 3.14 against invoke 3.0.3 (the write-up is the
`invoke-task-conventions` skill, "A task may not run anything that waits for typed input"):

1. invoke echoes stdin itself on a non-pty run while the child reads `/dev/tty`, so the two race for
   every keystroke — the password is printed and the child never sees it, so it re-prompts.
2. On Python 3.14 invoke's stdin thread dies on the first keystroke: `terminals.bytes_to_read()`
   hands `fcntl.ioctl(FIONREAD)` a 2-byte buffer for a 4-byte result, which 3.14 hardened into
   `SystemError: buffer overflow`. Nothing is forwarded to the child, pty or not, and it waits
   forever. Upstream pyinvoke/invoke#1070, unreleased as of invoke 3.0.3.

`pty=True` appears to fix the first and does nothing for the second, which is what made it read as
the correct pattern right up until the interpreter moved under it — and this package is installed as
a uv tool on the family's default interpreter, 3.14. Both call sites were credential prompts, the
worst place for a silent hang.

The fix is not to accommodate the interactivity but to step out of invoke's way: a plain subprocess
inheriting this process's stdin, stdout and stderr owns the terminal for the duration, exactly as if
the command had been typed at the shell. Echo suppression is the child's own business and nothing
races it for the keystrokes. `power-user-linux-setup`'s `util.run_interactive()` is the same shape,
found the expensive way on a first `inv wsl.install` that hung after the sudo prompt with the
password echoed in plain text."""

import shlex
import subprocess

from invoke import Exit


def run_interactive(command: str) -> None:
    """Run `command` with the real terminal attached, and stop with its exit code if it fails.

    The command is printed first, the way every effectful command in this package is echoed: what
    ran should be visible and copy-pasteable. Nothing is captured, so nothing here can leak what the
    child prompted for — the child talks to the terminal directly."""
    print(command, flush=True)
    completed = subprocess.run(shlex.split(command), check=False)
    if completed.returncode != 0:
        raise Exit(code=completed.returncode)

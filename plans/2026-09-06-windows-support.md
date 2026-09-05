---
status: idea
updated: 2026-09-06
---

# Windows support, and why it is not a priority

## Context

Until 2026-09-06 this package declared no platform at all, so what it supported was whatever the one
Ubuntu runner happened to prove. That pass added `Operating System :: POSIX :: Linux` and
`Operating System :: MacOS` to `pyproject.toml`, each backed by a CI job. **Windows was deliberately
left out, and this file is the reasoning** — so the omission reads as a decision rather than as
something nobody got to.

**The user's call, 2026-09-06: worth writing down, not worth doing.** No machine in this family runs
Windows, and every consumer is a personal repo on this one Linux workstation.

## The surprise: the dependencies are not the blocker

The natural assumption is that a Python package wrapping eight command-line tools cannot go to
Windows because the tools do not. Measured from PyPI the same day, that is false — **every gate tool
publishes a Windows wheel or binary**:

| distribution    | Windows                                                                    |
| --------------- | -------------------------------------------------------------------------- |
| `ruff`          | `win32`, `win_amd64`, `win_arm64`                                          |
| `dprint-py`     | `win_amd64`, `win_arm64`                                                   |
| `zizmor`        | `win32`, `win_amd64`                                                       |
| `shellcheck-py` | `win_amd64`                                                                |
| `shfmt-py`      | `win_amd64`                                                                |
| `hadolint-py`   | `win_amd64`                                                                |
| `actionlint-py` | sdist, with `win32-AMD64`/`win32-ARM64` entries in its own `checksums.cfg` |
| `basedpyright`  | `py3-none-any`                                                             |

So the blockers are **this package's own POSIX assumptions**, which is the more actionable finding:
they are ours to fix rather than upstream's to ship.

## What actually breaks

Read from the source 2026-09-06, not run — nothing here has been executed on Windows, and that is
itself the point of §"What it would take".

1. **`agents._claude_env_file_path` builds an invalid filename.** It slugs a project path with
   `str(base).replace("/", "-")`. A Windows path is `C:\Users\...`, so the separator is never
   replaced and the drive colon survives — and `:` is illegal in a Windows filename. The env cache
   file cannot be created, so `agents.wire-claude-hook` fails on the one platform-specific line it
   has.
2. **`agents._direnv_hook_command` assumes a POSIX shell**, `unset A B C; direnv export zsh > file`.
   No `cmd`/PowerShell equivalent is emitted, and `direnv` itself is not a Windows tool in the way
   the hook assumes.
3. **`interactive.run_interactive` splits with `shlex`**, whose quoting rules are POSIX. Windows
   wants `subprocess.list2cmdline` semantics, and getting this wrong on a credential prompt — which
   is what that module exists for — is the worst place to be approximately right.
4. **Both bootstrap scripts are bash.** `bootstrap.sh` and the generated `bootstrap-repo-tasks.sh`
   are `#!/usr/bin/env bash`, and `selfinstall`'s `_STAMP_TEMPLATE` writes a bash script and
   `chmod +x`es it — a mode bit Windows does not have.
5. **The clean-OS tier is Linux containers.** `tests/integration/` builds a Debian image, so the
   tier that exists precisely to prove a fresh machine works has no Windows counterpart. Whatever
   Windows support meant, it would be unverified in exactly the way this repo tags `[UNVERIFIED:` —
   and the 2026-09-06 audit's headline finding was a gate that had never once been run on a machine
   that lacked its tools.

Not blockers, checked and cleared: nothing in the package shells out to coreutils, and there is no
date, time or locale handling anywhere — so the two classic portability traps do not apply.

## What it would take

Roughly, in dependency order:

1. Replace the path slug with something drive- and separator-safe, and give `interactive.py` a
   Windows branch.
2. Decide what the Claude hook even means without `direnv` — probably "nothing, and say so", the way
   `direnv.allow` already no-ops when `direnv` is absent.
3. A PowerShell bootstrap, or a documented `uv`-only path that skips the shell script.
4. A `windows-latest` unit job, which is the cheap part and the only thing that would make the claim
   real.
5. Decide what `quality.shell-check` means on a repo with no shell scripts, which is every Windows
   repo — it already no-ops, so likely nothing.

[DECISION: **do not claim Windows until items 1–4 are done.** A classifier without a job is the
claim this repo spent 2026-09-06 removing from its own gate docs, and adding one here would
reintroduce the same shape one file over. Linux and macOS each have a job; Windows gets a classifier
when it gets a job.]

[DEFERRED: all of it, at the user's direction 2026-09-06. No machine in this family runs Windows and
no consumer is on it, so every item above is speculative work against a need nobody has. Recorded
because the finding that the dependencies already support Windows is genuinely surprising and would
otherwise be re-derived by whoever asks next — the expensive half of this question is already
answered.]

## Recommended direction

Leave it. Revisit if a Windows consumer ever appears, and start from §"What actually breaks", which
is a real list rather than a guess — but re-measure the wheel table first, since it is the half that
moves.

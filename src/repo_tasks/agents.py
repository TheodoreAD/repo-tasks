"""AI coding agent facility: installing this repo's own skills for every agent.

`wire_claude_hook` used to live here, writing a Claude Code hook and an absolute CLAUDE_ENV_FILE
path into each repo's committed .claude/settings.json. Retired 2026-11-25: it published the
developer's home directory in every repo that ran it, and a repo is the wrong place for machine
behavior. Per-directory venv activation for Claude Code is now a user-level hook that
power-user-linux-setup deploys (`[packages.claude-direnv-hook]`), which covers every repo with an
allowed .envrc and writes nothing into any of them."""

import os
import shutil
import subprocess
from pathlib import Path

from invoke import Context, task

# A repo's own skills are authored in skills/<name>/ — the same layout a published skills repo uses,
# and one the `skills` CLI discovers — and installed per clone into .agents/skills/, which every
# agent reads natively except Claude Code, which gets one link per skill in .claude/skills/. Both
# install targets and the CLI's skills-lock.json are gitignored, so a developer trying another skill
# in the project with a plain `skills add` changes nothing git tracks.
_SKILLS_SOURCE = "skills"

# Both names, and nothing else. With claude-code alone the CLI copies into .claude/skills and leaves
# .agents/skills empty; with `universal` beside it, it writes the copy there and links Claude Code to
# it — a junction on Windows, which needs no privilege. Measured on CLI 1.9.0.
_SKILLS_AGENTS = ("universal", "claude-code")

# The CLI reports usage unless told not to, and this runs unattended on every clone.
_SKILLS_ENV = {"DO_NOT_TRACK": "1", "DISABLE_TELEMETRY": "1"}


def authored_skills(base: Path) -> list[str]:
    """Names of the skills authored under <base>/skills/, one per directory holding a SKILL.md."""
    source = base / _SKILLS_SOURCE
    if not source.is_dir():
        return []
    return sorted(md.parent.name for md in source.glob("*/SKILL.md"))


def skills_cli() -> list[str] | None:
    """The argv prefix that runs the `skills` CLI here, or None when neither it nor npx is on PATH.

    The resolved path, not the bare name, so Windows finds `skills.cmd` without a shell.
    """
    if found := shutil.which("skills"):
        return [found]
    if npx := shutil.which("npx"):
        return [npx, "--yes", "skills"]
    return None


@task(help={"dir": "Project directory whose skills/ to install (default: current directory)"})
def install_skills(c: Context, dir: str = "."):  # noqa: A002
    """Install this repo's own skills, authored in skills/<name>/, for every agent: one copy per skill
    in .agents/skills/ and a link per skill in .claude/skills/ for Claude Code, through the `skills`
    CLI. Re-run after editing a skill — the installed copies do not follow the source, and
    `skills update` skips local sources. A no-op in a repo with no skills/ directory.

    Runs the CLI directly rather than through `c.run`, with an argument list and no shell, so the
    same call works under cmd.exe on Windows.
    """
    base = Path(dir).expanduser().resolve()
    names = authored_skills(base)
    if not names:
        print(f"[agents.install-skills] no skills/<name>/SKILL.md in {base} — nothing to install")
        return
    cli = skills_cli()
    if cli is None:
        print(
            f"[agents.install-skills] skipped {len(names)} skill(s): the `skills` CLI is not on PATH, "
            "and neither is npx. No agent sees this repo's skills until it is installed and this runs again."
        )
        return
    cmd = [*cli, "add", f"./{_SKILLS_SOURCE}", "--agent", *_SKILLS_AGENTS, "--skill", "*", "--yes"]
    result = subprocess.run(cmd, cwd=base, env={**os.environ, **_SKILLS_ENV}, check=False)
    if result.returncode != 0:
        raise SystemExit(f"[agents.install-skills] `skills add` exited {result.returncode}")
    print(f"[agents.install-skills] installed {', '.join(names)}")

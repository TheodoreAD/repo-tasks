"""AI coding agent facility: installing this repo's own skills for every agent, and wiring an agent
tool's shell execution to pick up this repo's direnv-managed environment (currently just Claude
Code; a second agent tool's own hook would land here too, alongside wire_claude_hook)."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TypedDict, cast

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
        print(f"[agents.install-skills] no skills/ in {base} — nothing to install")
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


def _claude_env_cache_dir() -> Path:
    """Resolved at call time, not import time, so an overridden HOME (the unit tier's
    `isolated_home` fixture) actually lands — a module-level constant would freeze the real home."""
    return Path.home() / ".cache" / "claude-code"


class _ClaudeHookEntry(TypedDict):
    type: str
    command: str


class _ClaudeHookGroup(TypedDict):
    matcher: str
    hooks: list[_ClaudeHookEntry]


class _ClaudeSettings(TypedDict, total=False):
    env: dict[str, str]
    hooks: dict[str, list[_ClaudeHookGroup]]


def _claude_env_file_path(base: Path) -> Path:
    """Deterministic per-project CLAUDE_ENV_FILE path — sanitized-abs-path scheme, same one
    Claude Code's own auto-memory directory uses, so two repos sharing a basename never collide."""
    slug = str(base).replace("/", "-").lstrip("-")
    return _claude_env_cache_dir() / f"{slug}-direnv-env"


def _direnv_hook_command(env_file: Path) -> str:
    return (
        f"unset DIRENV_DIR DIRENV_WATCHES DIRENV_DIFF DIRENV_FILE; direnv export zsh > {env_file} 2>/dev/null || true"
    )


@task(help={"dir": "Project directory to wire the hook for (default: current directory)"})
def wire_claude_hook(c: Context, dir: str = "."):  # noqa: A002
    """Wire Claude Code's Bash tool to auto-activate this project's direnv environment on every
    call, by writing <dir>/.claude/settings.json with env.CLAUDE_ENV_FILE and a PreToolUse/Bash
    hook that refreshes it from `direnv export zsh` before each command.

    Needed because Claude Code's Bash tool runs commands as non-interactive shells: direnv's
    normal shell hook never fires there, and a plain profile export gets clobbered by the
    harness's own captured-shell-snapshot PATH. CLAUDE_ENV_FILE is Claude Code's own mechanism for
    persisting environment changes across tool calls; refreshing it every call picks up `cd` and
    `.envrc` changes too, not just the session-start state. Merges into an existing settings.json
    rather than overwriting. No-ops if <dir>/.envrc doesn't exist, since there's nothing to
    activate.
    """
    base = Path(dir).expanduser().resolve()
    envrc = base / ".envrc"
    settings_path = base / ".claude" / "settings.json"
    env_file = _claude_env_file_path(base)
    hook_entry: _ClaudeHookEntry = {"type": "command", "command": _direnv_hook_command(env_file)}

    if not envrc.exists():
        print(f"[agents.wire-claude-hook] {envrc} not found — nothing to hook, skipping")
        return

    settings: _ClaudeSettings = (
        cast(_ClaudeSettings, json.loads(settings_path.read_text(encoding="utf-8"))) if settings_path.exists() else {}
    )
    env_ok = settings.get("env", {}).get("CLAUDE_ENV_FILE") == str(env_file)
    bash_group = next((g for g in settings.get("hooks", {}).get("PreToolUse", []) if g.get("matcher") == "Bash"), None)
    hook_ok = bash_group is not None and hook_entry in bash_group.get("hooks", [])
    if env_ok and hook_ok:
        print(f"[agents.wire-claude-hook] {settings_path} already configured")
        return

    settings.setdefault("env", {})["CLAUDE_ENV_FILE"] = str(env_file)
    pretooluse = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    bash_group = next((g for g in pretooluse if g.get("matcher") == "Bash"), None)
    if bash_group is None:
        new_group: _ClaudeHookGroup = {"matcher": "Bash", "hooks": []}
        bash_group = new_group
        pretooluse.append(bash_group)
    if hook_entry not in bash_group["hooks"]:
        bash_group["hooks"].append(hook_entry)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.touch(exist_ok=True)
    print(f"[agents.wire-claude-hook] {settings_path}: direnv hook configured ({env_file})")

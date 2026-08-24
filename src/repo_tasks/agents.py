"""AI coding agent facility: wiring an agent tool's shell execution to pick up this repo's
direnv-managed environment. Currently just Claude Code; a second agent tool's own hook would land
here too, alongside wire_claude_hook, rather than displacing it."""

import json
from pathlib import Path
from typing import TypedDict, cast

from invoke import task


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
def wire_claude_hook(c, dir="."):  # noqa: A002
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
        cast(_ClaudeSettings, json.loads(settings_path.read_text())) if settings_path.exists() else {}
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
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.touch(exist_ok=True)
    print(f"[agents.wire-claude-hook] {settings_path}: direnv hook configured ({env_file})")

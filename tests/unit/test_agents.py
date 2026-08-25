"""Tests for repo_tasks.agents: exercises wire_claude_hook's real filesystem/JSON logic against
tmp_path — the merge-into-existing-settings behavior and idempotency are the parts worth
covering directly."""

import json
from typing import cast

from repo_tasks import agents


def test_wire_claude_hook_noop_without_envrc(c, tmp_path, capsys):
    agents.wire_claude_hook.body(c, dir=str(tmp_path))
    assert not (tmp_path / ".claude").exists()
    assert "nothing to hook" in capsys.readouterr().out


def test_wire_claude_hook_writes_new_settings(c, tmp_path, isolated_home):
    (tmp_path / ".envrc").write_text("use flake\n")
    agents.wire_claude_hook.body(c, dir=str(tmp_path))

    settings_path = tmp_path / ".claude" / "settings.json"
    settings = cast(
        agents._ClaudeSettings,
        json.loads(settings_path.read_text()),
    )
    env_file = agents._claude_env_file_path(tmp_path.resolve())
    assert settings.get("env", {}).get("CLAUDE_ENV_FILE") == str(env_file)
    bash_group = next(g for g in settings.get("hooks", {}).get("PreToolUse", []) if g["matcher"] == "Bash")
    assert bash_group["hooks"][0]["command"] == agents._direnv_hook_command(env_file)
    assert env_file.exists()
    assert env_file.is_relative_to(isolated_home), "env-cache file must land under the fake HOME, never the real one"


def test_wire_claude_hook_merges_into_existing_settings(c, tmp_path):
    (tmp_path / ".envrc").write_text("use flake\n")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    existing = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
    (claude_dir / "settings.json").write_text(json.dumps(existing))

    agents.wire_claude_hook.body(c, dir=str(tmp_path))

    settings = cast(
        agents._ClaudeSettings,
        json.loads((claude_dir / "settings.json").read_text()),
    )
    matchers = {g["matcher"] for g in settings.get("hooks", {}).get("PreToolUse", [])}
    assert matchers == {"Write", "Bash"}


def test_wire_claude_hook_already_configured_is_idempotent(c, tmp_path, capsys):
    (tmp_path / ".envrc").write_text("use flake\n")
    agents.wire_claude_hook.body(c, dir=str(tmp_path))
    settings_path = tmp_path / ".claude" / "settings.json"
    before = settings_path.read_text()

    agents.wire_claude_hook.body(c, dir=str(tmp_path))
    assert settings_path.read_text() == before
    assert "already configured" in capsys.readouterr().out

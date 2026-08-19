"""Tests for repo_tasks.dev_env: asserts the exact command string `venv` builds via invoke's
MockContext, and exercises `claude_hook`'s real filesystem/JSON logic against tmp_path — the
merge-into-existing-settings behavior and idempotency are the parts worth covering directly."""

import json
from typing import cast

from invoke import MockContext, Result

from repo_tasks import dev_env


def test_venv_syncs_and_allows_direnv(monkeypatch):
    monkeypatch.setattr(dev_env, "_command_exists", lambda name: True)
    c = MockContext(run=True)
    dev_env.venv.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert c.run.call_args_list == [  # pyright: ignore[reportAttributeAccessIssue]
        (("uv sync",), {"echo": True}),
        (("direnv allow",), {"echo": True}),
    ]


def test_venv_skips_direnv_allow_when_direnv_missing(monkeypatch, capsys):
    monkeypatch.setattr(dev_env, "_command_exists", lambda name: False)
    c = MockContext(run=Result())
    dev_env.venv.body(c)  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    c.run.assert_called_once_with("uv sync", echo=True)  # pyright: ignore[reportAttributeAccessIssue]
    assert "direnv not found" in capsys.readouterr().out


def test_claude_hook_noop_without_envrc(tmp_path, capsys):
    c = MockContext()
    dev_env.claude_hook.body(c, dir=str(tmp_path))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert not (tmp_path / ".claude").exists()
    assert "nothing to hook" in capsys.readouterr().out


def test_claude_hook_writes_new_settings(tmp_path):
    (tmp_path / ".envrc").write_text("use flake\n")
    c = MockContext()
    dev_env.claude_hook.body(c, dir=str(tmp_path))  # pyright: ignore[reportAny, reportFunctionMemberAccess]

    settings_path = tmp_path / ".claude" / "settings.json"
    settings = cast(
        dev_env._ClaudeSettings,  # pyright: ignore[reportPrivateUsage]
        json.loads(settings_path.read_text()),
    )
    env_file = dev_env._claude_env_file_path(tmp_path.resolve())  # pyright: ignore[reportPrivateUsage]
    assert settings.get("env", {}).get("CLAUDE_ENV_FILE") == str(env_file)
    bash_group = next(g for g in settings.get("hooks", {}).get("PreToolUse", []) if g["matcher"] == "Bash")
    assert bash_group["hooks"][0]["command"] == dev_env._direnv_hook_command(env_file)  # pyright: ignore[reportPrivateUsage]
    assert env_file.exists()


def test_claude_hook_merges_into_existing_settings(tmp_path):
    (tmp_path / ".envrc").write_text("use flake\n")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    existing = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
    (claude_dir / "settings.json").write_text(json.dumps(existing))

    c = MockContext()
    dev_env.claude_hook.body(c, dir=str(tmp_path))  # pyright: ignore[reportAny, reportFunctionMemberAccess]

    settings = cast(
        dev_env._ClaudeSettings,  # pyright: ignore[reportPrivateUsage]
        json.loads((claude_dir / "settings.json").read_text()),
    )
    matchers = {g["matcher"] for g in settings.get("hooks", {}).get("PreToolUse", [])}
    assert matchers == {"Write", "Bash"}


def test_claude_hook_already_configured_is_idempotent(tmp_path, capsys):
    (tmp_path / ".envrc").write_text("use flake\n")
    c = MockContext()
    dev_env.claude_hook.body(c, dir=str(tmp_path))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    settings_path = tmp_path / ".claude" / "settings.json"
    before = settings_path.read_text()

    dev_env.claude_hook.body(c, dir=str(tmp_path))  # pyright: ignore[reportAny, reportFunctionMemberAccess]
    assert settings_path.read_text() == before
    assert "already configured" in capsys.readouterr().out

"""Tests for repo_tasks.agents: exercises wire_claude_hook's real filesystem/JSON logic against
tmp_path — the merge-into-existing-settings behavior and idempotency are the parts worth
covering directly — and the command install_skills hands the `skills` CLI."""

import json
import subprocess
from typing import cast, final

import pytest

from repo_tasks import agents


def test_wire_claude_hook_noop_without_envrc(c, tmp_path, capsys):
    agents.wire_claude_hook.body(c, dir=str(tmp_path))
    assert not (tmp_path / ".claude").exists()
    assert "nothing to hook" in capsys.readouterr().out


def test_wire_claude_hook_writes_new_settings(c, tmp_path, isolated_home):
    (tmp_path / ".envrc").write_text("use flake\n", encoding="utf-8")
    agents.wire_claude_hook.body(c, dir=str(tmp_path))

    settings_path = tmp_path / ".claude" / "settings.json"
    settings = cast(
        agents._ClaudeSettings,
        json.loads(settings_path.read_text(encoding="utf-8")),
    )
    env_file = agents._claude_env_file_path(tmp_path.resolve())
    assert settings.get("env", {}).get("CLAUDE_ENV_FILE") == str(env_file)
    bash_group = next(g for g in settings.get("hooks", {}).get("PreToolUse", []) if g["matcher"] == "Bash")
    assert bash_group["hooks"][0]["command"] == agents._direnv_hook_command(env_file)
    assert env_file.exists()
    assert env_file.is_relative_to(isolated_home), "env-cache file must land under the fake HOME, never the real one"


def test_wire_claude_hook_merges_into_existing_settings(c, tmp_path):
    (tmp_path / ".envrc").write_text("use flake\n", encoding="utf-8")
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    existing = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
    (claude_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

    agents.wire_claude_hook.body(c, dir=str(tmp_path))

    settings = cast(
        agents._ClaudeSettings,
        json.loads((claude_dir / "settings.json").read_text(encoding="utf-8")),
    )
    matchers = {g["matcher"] for g in settings.get("hooks", {}).get("PreToolUse", [])}
    assert matchers == {"Write", "Bash"}


def test_wire_claude_hook_already_configured_is_idempotent(c, tmp_path, capsys):
    (tmp_path / ".envrc").write_text("use flake\n", encoding="utf-8")
    agents.wire_claude_hook.body(c, dir=str(tmp_path))
    settings_path = tmp_path / ".claude" / "settings.json"
    before = settings_path.read_text(encoding="utf-8")

    agents.wire_claude_hook.body(c, dir=str(tmp_path))
    assert settings_path.read_text(encoding="utf-8") == before
    assert "already configured" in capsys.readouterr().out


# install_skills — the subprocess is replaced; what is asserted is the command it would run.


def _skill(base, name):
    (base / "skills" / name).mkdir(parents=True)
    (base / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")


@final
class _Recorder:
    def __init__(self, returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.returncode = returncode

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, self.returncode)


def test_authored_skills_lists_only_directories_holding_a_skill_md(tmp_path):
    _skill(tmp_path, "b-skill")
    _skill(tmp_path, "a-skill")
    (tmp_path / "skills" / "notes").mkdir()
    (tmp_path / "skills" / "README.md").write_text("x", encoding="utf-8")
    assert agents.authored_skills(tmp_path) == ["a-skill", "b-skill"]


def test_install_skills_is_a_noop_without_a_skills_directory(c, tmp_path, capsys, monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr("subprocess.run", recorder)
    agents.install_skills.body(c, dir=str(tmp_path))
    assert recorder.calls == []
    assert "nothing to install" in capsys.readouterr().out


def test_install_skills_names_universal_beside_claude_code_and_pins_telemetry_off(c, tmp_path, monkeypatch):
    # Both agents are load-bearing: with claude-code alone the CLI copies into .claude/skills and
    # leaves .agents/skills, which every other agent reads, empty.
    _skill(tmp_path, "demo")
    recorder = _Recorder()
    monkeypatch.setattr(agents, "skills_cli", lambda: ["/bin/skills"])
    monkeypatch.setattr("subprocess.run", recorder)

    agents.install_skills.body(c, dir=str(tmp_path))

    [(cmd, kwargs)] = recorder.calls
    expected = ["/bin/skills", "add", "./skills", "--agent", "universal", "claude-code"]
    assert cmd == [*expected, "--skill", "*", "--yes"]
    assert kwargs["cwd"] == tmp_path.resolve()
    env = cast("dict[str, str]", kwargs["env"])
    assert env["DO_NOT_TRACK"] == "1"
    assert env["DISABLE_TELEMETRY"] == "1"


def test_install_skills_skips_with_a_sentence_when_no_cli_exists(c, tmp_path, capsys, monkeypatch):
    _skill(tmp_path, "demo")
    recorder = _Recorder()
    monkeypatch.setattr(agents, "skills_cli", lambda: None)
    monkeypatch.setattr("subprocess.run", recorder)

    agents.install_skills.body(c, dir=str(tmp_path))

    assert recorder.calls == []
    assert "not on PATH" in capsys.readouterr().out


def test_install_skills_fails_loudly_when_the_cli_does(c, tmp_path, monkeypatch):
    _skill(tmp_path, "demo")
    monkeypatch.setattr(agents, "skills_cli", lambda: ["/bin/skills"])
    monkeypatch.setattr("subprocess.run", _Recorder(returncode=1))
    with pytest.raises(SystemExit):
        agents.install_skills.body(c, dir=str(tmp_path))


def test_skills_cli_falls_back_to_npx(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/npx" if name == "npx" else None)
    assert agents.skills_cli() == ["/usr/bin/npx", "--yes", "skills"]


def test_skills_cli_is_none_without_either(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert agents.skills_cli() is None

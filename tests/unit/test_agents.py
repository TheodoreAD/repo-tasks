"""Tests for repo_tasks.agents: the command install_skills hands the `skills` CLI."""

import subprocess
from typing import cast, final

import pytest

from repo_tasks import agents

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

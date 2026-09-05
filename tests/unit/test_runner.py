"""Report mode's own tests.

These run real subprocesses rather than a `MockContext`, deliberately. The whole module is about
what a command's output and exit code turn into, and a mock supplies both — so a mocked test here
would assert that the fixture came back, which is the blind spot that let `docker login` ship a hang
past a green suite for five days. The commands are `printf`/`exit` one-liners, so the cost is
milliseconds.
"""

import re

import pytest
from invoke import Collection, Config, Context, Exit
from invoke.exceptions import UnexpectedExit

from repo_tasks import runner
from repo_tasks.runner import ReportingLocal

_DURATION = re.compile(r"\d+\.\ds")


def _fields(line: str) -> list[str]:
    """A successful report line's fields, with the duration collapsed to `<s>`.

    The duration is measured elapsed time, so pinning it to `0.0s` asserts that the machine was
    idle — which CI disproved: `unit (3.13)` alone went red on a `0.1s` for a `seq 3` while three
    other interpreters passed the identical commit. The field's _shape_ is what is worth asserting,
    and is asserted here rather than dropped."""
    fields = line.split(" | ")
    assert len(fields) >= 3, f"not a report line: {line!r}"
    assert _DURATION.fullmatch(fields[2]), f"no duration in the third field of {line!r}"
    return [*fields[:2], "<s>", *fields[3:]]


def _context() -> Context:
    """A context that does not mirror stdin.

    `in_stream=False` is a test-harness concern, not a production one: invoke spawns a thread to
    forward this process's stdin to the child, and under pytest's capture that thread raises
    ("reading from stdin while output is captured"). Nothing in this package runs a command that
    reads stdin — `interactive.py` exists precisely because those must not go through `c.run`."""
    c = Context()
    c.config["run"]["in_stream"] = False
    return c


@pytest.fixture
def reporting() -> Context:
    """A context whose runner is the reporting one, as `__init__.py` wires it under the env var."""
    c = _context()
    c.config["runners"]["local"] = ReportingLocal
    runner.reset()
    return c


def test_enabled_follows_the_env_var(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("REPO_TASKS_RUN_REPORT", raising=False)
    assert not runner.enabled()
    monkeypatch.setenv("REPO_TASKS_RUN_REPORT", "1")
    assert runner.enabled()


def test_an_echoed_command_reports_one_line_and_folds_its_output(
    reporting: Context, capsys: pytest.CaptureFixture[str]
):
    # The folded text must not appear in the command itself, or the assertion below passes for the
    # wrong reason — the command is echoed on the report line whatever happens to its output.
    reporting.run("seq 3; echo All checks passed!", echo=True)
    out = capsys.readouterr().out
    assert "\n1\n" not in out, "a successful command's output should be folded away"
    lines = out.splitlines()
    assert len(lines) == 1, "one report line and nothing else"
    assert _fields(lines[0]) == ["seq 3; echo All checks passed!", "ok", "<s>", "All checks passed!"]


def test_the_summary_is_the_last_non_empty_line(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """The generic rule that replaced pytest-specific count parsing: whatever the tool printed
    last is its own summary, and blank trailing lines are not it."""
    reporting.run("printf 'noise\\n1 file reformatted\\n\\n\\n'", echo=True)
    assert capsys.readouterr().out.rstrip().endswith("| 1 file reformatted")


def test_a_command_with_no_output_gets_no_summary_column(reporting: Context, capsys: pytest.CaptureFixture[str]):
    reporting.run("true", echo=True)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert _fields(lines[0]) == ["true", "ok", "<s>"]


def test_a_failure_replays_everything_and_raises_exit(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """More than `UnexpectedExit`'s ten-line excerpt, and the verdict last so `| tail -3` on a red
    run names the command instead of showing whatever the tool happened to print."""
    with pytest.raises(Exit) as raised:
        reporting.run("printf 'line%s\\n' $(seq 1 25); exit 3", echo=True)
    assert raised.value.code == 3
    out = capsys.readouterr().out
    for n in (1, 13, 25):
        assert f"line{n}\n" in out, "every line of a failing command's output is replayed"
    assert out.splitlines()[-1].startswith("FAIL | printf")
    assert out.splitlines()[-1].endswith("exit=3 (output above)")


def test_a_warning_caller_keeps_its_output_and_its_exit_code(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """`warn=True` means the call site decides. `deps.lock` scrapes stderr for uv's moved-member
    hint, so the output is still replayed — but nothing is raised and it is not called a FAIL."""
    result = reporting.run("echo trouble >&2; exit 2", echo=True, warn=True)
    assert result.exited == 2
    captured = capsys.readouterr()
    assert "FAIL" not in captured.out
    assert "| exit=2 |" in captured.out
    assert "trouble" in captured.err


def test_pytest_exit_five_is_not_called_a_failure(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """The case the report line exists not to lie about: a repo with no tests yet, where
    `testing.py` accepts exit 5 as a pass."""
    reporting.run("echo 'no tests ran'; exit 5", echo=True, warn=True)
    line = capsys.readouterr().out.splitlines()[0]
    assert "FAIL" not in line
    assert "exit=5" in line


def test_an_unechoed_command_is_left_completely_alone(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """Internal queries — reading a branch, listing tracked files — pass `hide=True` and must stay
    silent. Reporting them would drown the output; gitflow.py alone runs 41 such commands."""
    result = reporting.run("echo internal-query", hide=True)
    assert result.stdout.strip() == "internal-query"
    assert capsys.readouterr().out == ""


def test_an_explicit_hide_false_keeps_the_command_streaming(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """Load-bearing, not redundant: it is how `test.coverage` keeps its report visible in report
    mode. A caller that names `hide` at all has said what it wants."""
    reporting.run("echo the-coverage-report", echo=True, hide=False)
    out = capsys.readouterr().out
    assert "the-coverage-report" in out, "an explicit hide=False must not be folded"
    assert "| ok |" not in out, "and gets invoke's own echo, not a report line"


def test_the_verdict_counts_the_commands_that_ran(reporting: Context, capsys: pytest.CaptureFixture[str]):
    reporting.run("true", echo=True)
    reporting.run("true", echo=True)
    capsys.readouterr()
    runner.verdict("quality.check")
    assert capsys.readouterr().out.startswith("quality.check | PASS | 2 steps |")


def test_the_verdict_is_silent_when_nothing_was_reported(capsys: pytest.CaptureFixture[str]):
    """Which is what "report mode is off" looks like from here — only `ReportingLocal` fills the
    ledger — so a gate body prints nothing at all under stock invoke."""
    runner.reset()
    runner.verdict("quality.check")
    assert capsys.readouterr().out == ""


def test_a_long_command_is_elided_in_the_middle(reporting: Context, capsys: pytest.CaptureFixture[str]):
    """actionlint over every workflow is the real case. Both ends identify it; the middle does
    not."""
    command = "echo " + " ".join(f".github/workflows/file{n}.yml" for n in range(20))
    reporting.run(command, echo=True)
    line = capsys.readouterr().out.splitlines()[0]
    assert line.startswith("echo .github/workflows/file0.yml")
    assert "..." in line
    assert len(line.split(" | ")[0]) <= runner._MAX_COMMAND


def test_stock_invoke_is_untouched_when_the_runner_is_not_installed(capsys: pytest.CaptureFixture[str]):
    """The property the whole design rests on: with no runner swap, an echoed command streams and
    a failure raises invoke's own UnexpectedExit, exactly as invoke documents."""
    c = _context()
    c.run("echo streamed-normally", echo=True)
    assert "streamed-normally" in capsys.readouterr().out
    with pytest.raises(UnexpectedExit):
        c.run("exit 7", echo=True)


def test_configure_installs_the_runner_on_a_collection_this_package_did_not_build(
    monkeypatch: pytest.MonkeyPatch,
):
    """The half the env var cannot do by itself. A consumer that hand-builds its own namespace gets
    report mode from this call and from nothing else — `__init__.py` reaches `ns` and no other
    object."""
    monkeypatch.setenv("REPO_TASKS_RUN_REPORT", "1")
    namespace = Collection()
    assert runner.configure(namespace) is True
    assert namespace.configuration()["runners"]["local"] is ReportingLocal


def test_configure_touches_nothing_when_report_mode_is_off(monkeypatch: pytest.MonkeyPatch):
    """Stock invoke unless asked, extended to a consumer's namespace: no `runners` key at all, so a
    consumer can prove the claim by reading its own config rather than by trusting a branch."""
    monkeypatch.delenv("REPO_TASKS_RUN_REPORT", raising=False)
    namespace = Collection()
    assert runner.configure(namespace) is False
    assert "runners" not in namespace.configuration()


def test_a_context_built_from_a_configured_collection_actually_reports(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    """End to end through invoke rather than through the dict `configure` just wrote: it is invoke
    that decides `runners.local` is the key a Context resolves its runner from, so asserting the key
    back only proves this module is self-consistent."""
    monkeypatch.setenv("REPO_TASKS_RUN_REPORT", "1")
    namespace = Collection()
    runner.configure(namespace)
    c = Context(config=Config(overrides=namespace.configuration()))
    c.config["run"]["in_stream"] = False
    runner.reset()
    c.run("echo wired", echo=True)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert _fields(lines[0]) == ["echo wired", "ok", "<s>", "wired"]


def test_two_report_lines_differing_only_in_the_clock_are_the_same_line():
    """The regression `_fields` exists for, asserted rather than trusted: the tests above pinned
    `0.0s`, which held on an idle machine for a day and then failed one CI interpreter on `0.1s`
    while three others passed the same commit."""
    idle = "basedpyright | ok | 0.0s | 0 errors, 0 warnings, 0 notes"
    loaded = "basedpyright | ok | 12.3s | 0 errors, 0 warnings, 0 notes"
    assert _fields(idle) == _fields(loaded)


def test_a_line_with_no_duration_is_not_accepted_as_a_report_line():
    """Otherwise `_fields` would launder a genuinely broken line into a passing assertion, which is
    the way a loosened matcher usually goes wrong."""
    with pytest.raises(AssertionError):
        _fields("basedpyright | ok | not-a-duration | 0 errors")

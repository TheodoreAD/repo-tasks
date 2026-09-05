"""Tests for repo_tasks.steps: the folded/replayed output of one gate step and the verdict line.

Assertions are on what reaches the terminal (capsys), since the terminal is the contract — what a
`| tail -3` on the gate shows is the whole reason the module exists — plus the call shape handed to
`c.run`, which is what decides whether output is captured or streamed."""

import pytest
from invoke import Config, Exit, MockContext, Result

from repo_tasks import steps


@pytest.fixture(autouse=True)
def fresh_ledger():
    """Every test is its own run: the ledger is process state, and the whole unit tier runs gate
    steps through the same interpreter."""
    steps.reset()
    yield
    steps.reset()


def _verbose_context(result: Result) -> MockContext:
    return MockContext(config=Config(overrides={"quality": {"verbose": True}}), run=result)


def test_a_passing_step_folds_its_output_and_prints_one_line(capsys):
    c = MockContext(run=Result(stdout="All checks passed!\n", exited=0))
    result = steps.run_step(c, "ruff check .")
    assert result.exited == 0
    c.run.assert_called_once_with("ruff check .", hide=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]
    out = capsys.readouterr().out
    assert "All checks passed!" not in out
    lines = out.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("ruff check . ...")
    assert " ok  " in lines[0]
    assert lines[0].rstrip().endswith("s")  # the wall time


def test_a_failing_step_replays_its_output_and_the_verdict_is_the_last_line(capsys):
    c = MockContext(run=Result(stdout="src/x.py:1: error: bad\n", stderr="1 error\n", exited=1))
    with pytest.raises(Exit) as exc_info:
        steps.run_step(c, "basedpyright")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines[0].startswith("basedpyright ...")
    assert lines[0].endswith("FAIL  exit 1")
    # The tool's own output, in full, between its step line and the verdict.
    assert "src/x.py:1: error: bad" in lines[1:-1]
    assert lines[-1] == "FAIL  basedpyright exited 1 (output above)"
    # stderr replays to stderr, so a run that pipes only stdout still sees it on the terminal.
    assert captured.err == "1 error\n"


def test_replay_terminates_an_unterminated_last_line(capsys):
    # Otherwise the verdict would be glued onto the tool's last line — the one line tail shows.
    c = MockContext(run=Result(stdout="no newline at the end", exited=2))
    with pytest.raises(Exit):
        steps.run_step(c, "cmd")
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2] == "no newline at the end"
    assert lines[-1].startswith("FAIL  cmd exited 2")


def test_ok_codes_widen_what_counts_as_a_pass(capsys):
    # pytest's 5, "no tests collected", is the case: a pass for a repo with no tests yet.
    c = MockContext(run=Result(exited=5))
    steps.run_step(c, "pytest", ok=frozenset({0, 5}))
    assert " ok  " in capsys.readouterr().out


def test_a_note_lands_on_the_step_line_and_on_the_verdict(capsys):
    c = MockContext(run=Result(stdout="=== 465 passed in 4.2s ===\n", exited=0))
    steps.run_step(c, "pytest", note=lambda result: "465 passed" if result.ok else None)
    steps.verdict("quality.check")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("465 passed")
    assert lines[1].startswith("quality.check: PASS  1 step, 465 passed, ")


def test_the_verdict_counts_every_passing_step_and_sums_their_time(capsys):
    c = MockContext(run=Result(exited=0))
    for command in ("a", "b", "c"):
        steps.run_step(c, command)
    steps.verdict("quality.precommit")
    last = capsys.readouterr().out.splitlines()[-1]
    assert last.startswith("quality.precommit: PASS  3 steps, ")
    assert last.endswith("s")


def test_verbose_streams_instead_of_folding(capsys):
    # echo, no hide: invoke prints the command and the tool's output reaches the terminal; the
    # step line then follows the output rather than bracketing it.
    c = _verbose_context(Result(stdout="streamed by invoke, not by us\n", exited=0))
    steps.run_step(c, "ruff check .")
    c.run.assert_called_once_with("ruff check .", echo=True, warn=True)  # pyright: ignore[reportAttributeAccessIssue]
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("ruff check . ...")
    assert " ok  " in lines[0]


def test_verbose_does_not_replay_what_already_streamed(capsys):
    c = _verbose_context(Result(stdout="already on the terminal\n", exited=1))
    with pytest.raises(Exit):
        steps.run_step(c, "cmd")
    lines = capsys.readouterr().out.splitlines()
    assert "already on the terminal" not in lines
    assert lines[-1] == "FAIL  cmd exited 1 (output above)"


def test_verbose_is_off_without_the_config_key():
    # A hand-built Collection (or a MockContext) never declares `quality.verbose`; quiet is the
    # default and the absence of the key must not be an error.
    assert steps.verbose(MockContext(run=True)) is False
    assert steps.verbose(_verbose_context(Result(exited=0))) is True


def test_a_long_command_still_gets_dots_and_a_status(capsys):
    command = "hadolint " + " ".join(f"images/{i}/Dockerfile" for i in range(8))
    c = MockContext(run=Result(exited=0))
    steps.run_step(c, command)
    line = capsys.readouterr().out.splitlines()[0]
    assert line.startswith(f"{command} ... ok  ")


def test_a_failing_step_does_not_count_toward_the_verdict(capsys):
    c = MockContext(run=Result(exited=1))
    with pytest.raises(Exit):
        steps.run_step(c, "cmd")
    steps.verdict("quality.check")
    assert "PASS  0 steps, " in capsys.readouterr().out

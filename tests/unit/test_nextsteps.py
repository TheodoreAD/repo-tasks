"""Tests for repo_tasks.nextsteps: the shape of the block, which is the whole of what it owns.

Pinned exactly, including the leading blank line and the two-space bullets, because five modules
print through this and the reason it exists is that they were each printing their own version of
it. A shape nobody asserts is a shape that drifts back apart."""

from repo_tasks.nextsteps import next_steps


def test_the_block_is_a_blank_line_a_heading_and_one_bullet_per_step(capsys):
    next_steps("inv deps.lock", "inv venv.sync")
    assert capsys.readouterr().out == "\nNext steps:\n  - inv deps.lock\n  - inv venv.sync\n"


def test_a_preamble_joins_the_heading_rather_than_taking_its_own_line(capsys):
    # `trunkflow.cut` says "Nothing pushed. Next steps:" as one sentence — two lines would read as
    # two thoughts, and this is the difference the parameter exists for.
    next_steps("inv release.push-tag --tag v1.2.0", preamble="Nothing pushed.")
    assert capsys.readouterr().out == "\nNothing pushed. Next steps:\n  - inv release.push-tag --tag v1.2.0\n"


def test_a_heading_with_no_steps_under_it_is_still_a_heading(capsys):
    # `configs.diff` builds its list conditionally, so an empty call is reachable rather than
    # hypothetical: it should not crash, and it should not invent a bullet.
    next_steps()
    assert capsys.readouterr().out == "\nNext steps:\n"

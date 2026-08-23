"""Fixtures for the unit tier: no subprocesses, no network, no Docker, nothing outside tmp_path.

The whole tier asserts on the exact command string a task builds, so `c` — invoke's `MockContext`
with `run` stubbed — is the one fixture nearly every test wants. A test needing a *specific* run
result (a particular `Result`, or a dict of command → result) builds its own `MockContext` inline
instead; that is the intended split, not an oversight. See contributing/test-tiers.md.
"""

import pytest
from invoke import MockContext


@pytest.fixture
def c() -> MockContext:
    """A MockContext whose `run` accepts any command and reports success, so a task under test
    executes end to end and `c.run.assert_called_once_with(...)` can pin what it built."""
    return MockContext(run=True)
